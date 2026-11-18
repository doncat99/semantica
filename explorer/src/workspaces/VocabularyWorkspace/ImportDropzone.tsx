/**
 * ImportDropzone.tsx
 *
 * Drag & drop upload zone for SKOS .ttl / .rdf files.
 * Styled for the Palantir dark theme.
 */
import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import { UploadCloud, CheckCircle2, Loader2 } from 'lucide-react';
import { useImportVocabulary } from './queries';
import type { ImportResponse } from './types';

export const ImportDropzone: React.FC = () => {
  const [file, setFile] = useState<File | null>(null);
  const [importResult, setImportResult] = useState<ImportResponse | null>(null);
  const importMutation = useImportVocabulary();

  const onDrop = useCallback((acceptedFiles: File[]) => {
    if (acceptedFiles.length > 0) {
      const selectedFile = acceptedFiles[0];
      setFile(selectedFile);
      setImportResult(null);

      importMutation.mutate(selectedFile, {
        onSuccess: (data) => {
          setImportResult(data);
          setTimeout(() => {
            setFile(null);
            setImportResult(null);
          }, 4000);
        },
        onError: (err) => {
          console.error("Upload failed:", err);
          setFile(null);
        }
      });
    }
  }, [importMutation]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/turtle': ['.ttl'],
      'application/rdf+xml': ['.rdf', '.owl']
    },
    maxFiles: 1
  });

  return (
    <div>
      <div
        {...getRootProps()}
        style={{
          border: `2px dashed ${isDragActive ? 'var(--ws-accent)' : 'var(--ws-border)'}`,
          backgroundColor: isDragActive ? 'var(--ws-border)' : 'var(--ws-surface)',
          borderRadius: 8,
          padding: '16px 12px',
          textAlign: 'center',
          cursor: 'pointer',
          transition: 'all 0.2s ease',
        }}
      >
        <input {...getInputProps()} />

        {importMutation.isPending ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', color: 'var(--ws-text-muted)' }}>
            <Loader2 className="animate-spin" size={20} style={{ marginBottom: 6 }} />
            <span style={{ fontSize: 12 }}>Uploading {file?.name}…</span>
          </div>
        ) : importResult ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', color: 'var(--ws-green)' }}>
            <CheckCircle2 size={20} style={{ marginBottom: 6 }} />
            <span style={{ fontSize: 12, fontWeight: 500 }}>Import Successful!</span>
            <span style={{ fontSize: 11, marginTop: 2, color: 'var(--ws-green)' }}>
              +{importResult.nodes_added} concepts · +{importResult.edges_added} links
            </span>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', color: 'var(--ws-text-muted)' }}>
            <UploadCloud size={20} style={{ marginBottom: 6, color: isDragActive ? 'var(--ws-accent)' : 'var(--ws-text-dim)' }} />
            <span style={{ fontSize: 12, fontWeight: 500, color: 'var(--ws-text)' }}>
              {isDragActive ? "Drop here…" : "Import Vocabulary"}
            </span>
            <span style={{ fontSize: 11, marginTop: 2 }}>.ttl or .rdf</span>
          </div>
        )}
      </div>
      {importMutation.isError && (
        <p style={{ color: 'var(--ws-red)', fontSize: 11, marginTop: 6, textAlign: 'center' }}>
          Upload failed. Check console.
        </p>
      )}
    </div>
  );
};
