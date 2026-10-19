"""Native semantic snapshots on a host-owned TypeDB 3 driver.

TypeDB is not a Cypher backend. Only the explicit snapshot contract is exposed;
unsupported property-graph operations must not silently write another store.
"""
import json

from ..semantic_artifact_schema import SemanticArtifact, stable_digest
from ..utils.exceptions import ValidationError


SCHEMA = """define
attribute sem-key, value string;
attribute sem-scope, value string;
attribute sem-id, value string;
attribute sem-digest, value string;
attribute sem-json, value string;
attribute sem-kind, value string;
entity sem-head, owns sem-key @key, owns sem-id @card(1);
entity sem-snapshot, owns sem-key @key, owns sem-scope @card(1),
    owns sem-id @card(1), owns sem-digest @card(1), owns sem-json @card(1);
entity sem-record, owns sem-key @key, owns sem-id @card(1),
    owns sem-kind @card(1), owns sem-json @card(1);
relation sem-contains, relates snapshot @card(1), relates record @card(1);
sem-snapshot plays sem-contains:snapshot;
sem-record plays sem-contains:record;
"""


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _rows(tx, query, *keys):
    answer = tx.query(query).resolve()
    return [{key: row.get(key).as_attribute().get_value() for key in keys}
            for row in answer.as_concept_rows()]


class TypeDBStore:
    def __init__(self, *, driver, database, **config):
        if not database or not database.strip():
            raise ValidationError("typedb_database_required")
        self.driver, self.database = driver, database

    def connect(self, **options):
        return self.driver.databases.contains(self.database)

    def close(self):
        # The host owns the driver and may share it with its control repositories.
        pass

    def initialize_snapshot_storage(self):
        from typedb.driver import TransactionType

        if not self.driver.databases.contains(self.database):
            raise ValidationError("typedb_database_missing")
        existing = self.driver.databases.get(self.database).schema()
        if "entity sem-snapshot" not in existing:
            with self.driver.transaction(self.database, TransactionType.SCHEMA) as tx:
                tx.query(SCHEMA).resolve()
                tx.commit()

    @staticmethod
    def _head(tx, scope):
        found = _rows(tx, f'match $h isa sem-head, has sem-key {_json(scope)}, '
                      'has sem-id $id; select $id;', 'id')
        return found[0]['id'] if found else None

    def commit_snapshot(self, snapshot):
        """Commit all records and the CAS head in one TypeDB transaction.

        Concurrent updates touch the same keyed head. TypeDB rejects a conflicting
        commit; callers must reload/recompute, never replay stale writes blindly.
        """
        from typedb.driver import TransactionType

        value = SemanticArtifact.model_validate(snapshot).model_dump(mode='json')
        scope, sid = value['project_id'], value['snapshot_id']
        key = stable_digest([scope, sid])
        fingerprint = stable_digest(value)
        with self.driver.transaction(self.database, TransactionType.WRITE) as tx:
            current = self._head(tx, scope)
            old = _rows(tx, f'match $s isa sem-snapshot, has sem-key {_json(key)}, '
                        'has sem-digest $digest; select $digest;', 'digest')
            if old:
                if old[0]['digest'] != fingerprint:
                    raise ValidationError('immutable_snapshot_id_reused')
                return dict(snapshot_id=sid, head_snapshot_id=current,
                            digest=fingerprint, replayed=True)
            if current != value['base_snapshot_id']:
                raise ValidationError('stale_snapshot_head')
            tx.query(f'insert $s isa sem-snapshot, has sem-key {_json(key)}, '
                     f'has sem-scope {_json(scope)}, has sem-id {_json(sid)}, '
                     f'has sem-digest {_json(fingerprint)}, has sem-json {_json(_json(value))};').resolve()
            for kind, items in value.items():
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict) or 'id' not in item:
                        continue
                    record_key = stable_digest([scope, sid, kind, item['id']])
                    tx.query(f'match $s isa sem-snapshot, has sem-key {_json(key)}; '
                             f'insert $r isa sem-record, has sem-key {_json(record_key)}, '
                             f'has sem-id {_json(item["id"])}, has sem-kind {_json(kind)}, '
                             f'has sem-json {_json(_json(item))}; '
                             '$c isa sem-contains, links (snapshot: $s, record: $r);').resolve()
            if current is None:
                tx.query(f'insert $h isa sem-head, has sem-key {_json(scope)}, '
                         f'has sem-id {_json(sid)};').resolve()
            else:
                tx.query(f'match $h isa sem-head, has sem-key {_json(scope)}, '
                         f'has sem-id $old; delete has $old of $h; '
                         f'insert $h has sem-id {_json(sid)};').resolve()
            tx.commit()
        return dict(snapshot_id=sid, head_snapshot_id=sid,
                    digest=fingerprint, replayed=False)

    def read_snapshot(self, scope_id, snapshot_id=None):
        from typedb.driver import TransactionType

        with self.driver.transaction(self.database, TransactionType.READ) as tx:
            sid = snapshot_id if snapshot_id is not None else self._head(tx, scope_id)
            if sid is None:
                return None
            key = stable_digest([scope_id, sid])
            found = _rows(tx, f'match $s isa sem-snapshot, has sem-key {_json(key)}, '
                          'has sem-json $payload, has sem-digest $digest; '
                          'select $payload,$digest;', 'payload', 'digest')
            if not found:
                if snapshot_id is None:
                    raise ValidationError('semantic_head_snapshot_missing')
                return None
            value = json.loads(found[0]['payload'])
            if stable_digest(value) != found[0]['digest']:
                raise ValidationError('semantic_snapshot_digest_mismatch')
            artifact = SemanticArtifact.model_validate(value)
            if artifact.project_id != scope_id or artifact.id != sid:
                raise ValidationError('semantic_snapshot_scope_mismatch')
            return artifact.model_dump(mode='json')

    def execute_query(self, *args, **kwargs):
        raise NotImplementedError('TypeDB uses native snapshots, not Cypher')
