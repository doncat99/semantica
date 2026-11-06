# Ontology revision management

Knowledge graph snapshots, AgentContext checkpoints, restoration, named graph tags,
and snapshot mutation logs have been removed. They have no replacement reader or writer.
Use native per-object knowledge storage and event temporal queries for knowledge data.

`OntologyVersionManager` remains the independent ontology revision owner. Its
`VersionStorage` backends accept only ontology revisions (`ontology_iri`, `structure`,
and revision metadata); aggregate knowledge graph payloads are rejected on write
and read. Existing knowledge snapshot databases must be removed by an explicit
offline cleanup after verifying active readers and preserving original materials.


### Basic Ontology Versioning

```python
from semantica.change_management import OntologyVersionManager

# Initialize ontology version manager
ont_manager = OntologyVersionManager()

# Create an ontology
financial_ontology = {
    "uri": "https://bank.com/ontology",
    "version_info": {"version": "1.0", "date": "2024-01-30"},
    "structure": {
        "classes": ["Account", "Customer", "Transaction"],
        "properties": ["accountNumber", "balance", "amount"],
        "individuals": ["SavingsAccount", "CheckingAccount"],
        "axioms": ["Account belongsTo exactly 1 Customer"]
    }
}

# Create versioned snapshot
ont_snapshot = ont_manager.create_snapshot(
    financial_ontology,
    version_label="financial_v1.0",
    author="architect@bank.com",
    description="Initial financial ontology"
)
```

---

### 1. ChangeLogEntry

Standardized metadata structure for version changes with validation.

```python
from semantica.change_management import ChangeLogEntry

# Create a change log entry
entry = ChangeLogEntry.create_now(
    author="developer@company.com",
    description="Updated entity relationships based on new requirements",
    change_id="TICKET-123"  # Optional: link to issue tracker
)

print(f"Timestamp: {entry.timestamp}")
print(f"Author: {entry.author}")
print(f"Description: {entry.description}")
```

**Validation Features:**
- ISO 8601 timestamp format enforcement
- Email validation for authors
- Description length limits (500 characters)
- Optional change ID for linking to external systems

### 4. OntologyVersionManager

Advanced ontology version management with structural comparison.

```python
from semantica.change_management import OntologyVersionManager

# Initialize ontology manager
manager = OntologyVersionManager(storage_path="ontology_versions.db")

# Create ontology snapshot
snapshot = manager.create_snapshot(
    ontology_data,
    version_label="ont_v1.0",
    author="architect@company.com",
    description="Initial ontology design"
)

# Compare ontology versions
diff = manager.compare_versions("ont_v1.0", "ont_v2.0")
print(f"Classes added: {diff['classes_added']}")
print(f"Properties added: {diff['properties_added']}")
print(f"Axioms modified: {diff['axioms_modified']}")
```

---

## Ontology Versioning

### Creating Ontology Snapshots

```python
from semantica.change_management import OntologyVersionManager

manager = OntologyVersionManager(storage_path="ontology_versions.db")

# Financial domain ontology
financial_ontology = {
    "uri": "https://bank.com/ontology/financial",
    "version_info": {
        "version": "1.0",
        "date": "2024-01-30",
        "author": "Ontology Team"
    },
    "structure": {
        "classes": [
            "Account",
            "Customer",
            "Transaction",
            "Branch",
            "Employee"
        ],
        "properties": [
            "accountNumber",
            "balance",
            "transactionAmount",
            "customerName",
            "branchCode"
        ],
        "individuals": [
            "SavingsAccount",
            "CheckingAccount",
            "CreditAccount"
        ],
        "axioms": [
            "Account belongsTo exactly 1 Customer",
            "Transaction involves exactly 1 Account",
            "Customer hasAccount some Account"
        ]
    }
}

# Create initial ontology snapshot
ont_v1 = manager.create_snapshot(
    financial_ontology,
    version_label="financial_ont_v1.0",
    author="architect@bank.com",
    description="Initial financial domain ontology"
)
```

### Evolving Ontologies

```python
# Add compliance and risk management features
financial_ontology["structure"]["classes"].extend([
    "ComplianceCheck",
    "RiskProfile",
    "AuditLog"
])

financial_ontology["structure"]["properties"].extend([
    "riskScore",
    "complianceStatus",
    "auditTimestamp"
])

financial_ontology["structure"]["axioms"].extend([
    "Customer hasRiskProfile exactly 1 RiskProfile",
    "Transaction requiresCompliance some ComplianceCheck",
    "ComplianceCheck generatesAudit exactly 1 AuditLog"
])

financial_ontology["version_info"]["version"] = "2.0"

# Create updated ontology snapshot
ont_v2 = manager.create_snapshot(
    financial_ontology,
    version_label="financial_ont_v2.0",
    author="compliance@bank.com",
    description="Added compliance and risk management features"
)
```

### Comparing Ontology Versions

```python
# Get structural comparison
diff = manager.compare_versions("financial_ont_v1.0", "financial_ont_v2.0")

print("Ontology Evolution Summary:")
print(f"Classes added: {diff['classes_added']}")
print(f"Properties added: {diff['properties_added']}")
print(f"Individuals added: {diff['individuals_added']}")
print(f"Axioms added: {diff['axioms_added']}")

# Detailed changes
print("\nNew Classes:")
for cls in diff['classes_added']:
    print(f"  - {cls}")

print("\nNew Axioms:")
for axiom in diff['axioms_added']:
    print(f"  - {axiom}")
```

---

### Creating Standardized Change Logs

```python
from semantica.change_management import ChangeLogEntry

# Create change log entry with current timestamp
entry = ChangeLogEntry.create_now(
    author="developer@company.com",
    description="Updated patient medication based on lab results",
    change_id="JIRA-1234"
)

# Access metadata
print(f"Change ID: {entry.change_id}")
print(f"Timestamp: {entry.timestamp}")
print(f"Author: {entry.author}")
print(f"Description: {entry.description}")

# Manual timestamp (for historical records)
historical_entry = ChangeLogEntry(
    timestamp="2024-01-15T10:30:00Z",
    author="admin@company.com",
    description="System migration completed",
    change_id="MIGRATION-2024-01"
)
```

### Checksum Computation and Verification

```python
from semantica.change_management import compute_checksum, verify_checksum

# Compute checksum for data
data = {
    "entities": [...],
    "relationships": [...]
}

checksum = compute_checksum(data)
print(f"SHA-256 Checksum: {checksum}")

# Add checksum to snapshot
snapshot = data.copy()
snapshot["checksum"] = checksum

# Verify data integrity
is_valid = verify_checksum(snapshot)
print(f"Data integrity verified: {is_valid}")

# Detect tampering
snapshot["entities"][0]["name"] = "Modified"
is_valid = verify_checksum(snapshot)
print(f"Data integrity after modification: {is_valid}")  # False
```

### Example 2: Financial System (SOX Compliance)

```python
from semantica.change_management import OntologyVersionManager

# Initialize for financial ontology versioning
manager = OntologyVersionManager(storage_path="sox_compliant_ontology.db")

# Financial system ontology
financial_ontology = {
    "uri": "https://company.com/ontology/financial",
    "version_info": {"version": "1.0", "date": "2024-01-30"},
    "structure": {
        "classes": ["Account", "Transaction", "AuditLog", "ComplianceRule"],
        "properties": ["amount", "timestamp", "approver", "status"],
        "axioms": [
            "Transaction requiresApproval exactly 1 Approver",
            "Transaction generatesAuditLog exactly 1 AuditLog"
        ]
    }
}

# Create SOX-compliant ontology version
snapshot = manager.create_snapshot(
    financial_ontology,
    version_label="financial_v1.0_sox",
    author="cfo@company.com",
    description="SOX-compliant financial ontology with audit requirements"
)

# Track all ontology changes for compliance audits
print("SOX-compliant ontology version created")
```
