import { useRef, useState } from 'react';

import { ApiRequestError } from '../api/client';
import { mockUploadTransactions } from '../api/transactionUpload';
import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { Skeleton } from '../components/Skeleton';

const ACCEPTED_EXTENSIONS = ['.csv', '.tsv'];
const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // backend adapter/file_provider.py 와 동일한 상한

type UploadState =
  | { status: 'idle' }
  | { status: 'invalid'; fileName: string; message: string }
  | { status: 'uploading'; fileName: string }
  | { status: 'error'; message: string }
  | { status: 'empty' }
  | { status: 'success'; rowCount: number; skippedRowCount: number };

function validate(file: File): string | null {
  const hasAcceptedExtension = ACCEPTED_EXTENSIONS.some((ext) =>
    file.name.toLowerCase().endsWith(ext),
  );
  if (!hasAcceptedExtension) {
    return 'CSV 또는 TSV 파일만 업로드할 수 있습니다.';
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return '파일이 너무 큽니다 (최대 10MB).';
  }
  if (file.size === 0) {
    return '빈 파일입니다.';
  }
  return null;
}

export function TransactionUploadPage() {
  const [state, setState] = useState<UploadState>({ status: 'idle' });
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    const validationError = validate(file);
    if (validationError) {
      setState({ status: 'invalid', fileName: file.name, message: validationError });
      return;
    }

    setState({ status: 'uploading', fileName: file.name });
    try {
      const outcome = await mockUploadTransactions(file);
      setState(
        outcome.status === 'empty'
          ? { status: 'empty' }
          : {
              status: 'success',
              rowCount: outcome.rowCount,
              skippedRowCount: outcome.skippedRowCount,
            },
      );
    } catch (err: unknown) {
      const message =
        err instanceof ApiRequestError
          ? err.message
          : '업로드하지 못했습니다. 잠시 후 다시 시도해 주세요.';
      setState({ status: 'error', message });
    }
  };

  const reset = () => {
    setState({ status: 'idle' });
    if (inputRef.current) inputRef.current.value = '';
  };

  return (
    <section className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-1">거래내역 업로드</h2>
        <p className="text-sm text-gray-500">
          카드사에서 내려받은 CSV 또는 TSV 파일을 올리면 확정 지출을 계산합니다.
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
        <label className="inline-block">
          <span className="sr-only">거래내역 파일 선택</span>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS.join(',')}
            disabled={state.status === 'uploading'}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void handleFile(file);
            }}
            className="block w-full text-sm text-gray-700
              file:mr-4 file:rounded-lg file:border file:border-gray-300
              file:bg-white file:px-4 file:py-2 file:text-sm file:font-medium
              file:text-gray-700 hover:file:bg-gray-50 file:transition-colors"
          />
        </label>

        {state.status === 'uploading' && (
          <div className="space-y-2">
            <p className="text-sm text-gray-500">{state.fileName} 업로드 중…</p>
            <Skeleton className="h-4 w-full" />
          </div>
        )}

        {state.status === 'invalid' && (
          <p className="text-sm text-red-600">{state.message}</p>
        )}

        {state.status === 'error' && (
          <ErrorState message={state.message} onRetry={reset} />
        )}

        {state.status === 'empty' && (
          <EmptyState
            message="업로드한 파일에서 거래내역을 찾지 못했습니다. 헤더만 있거나 형식이 다른 것 같습니다."
            action={
              <Button variant="secondary" onClick={reset}>
                다른 파일 선택
              </Button>
            }
          />
        )}

        {state.status === 'success' && (
          <div className="bg-emerald-50 rounded-xl border border-emerald-200 p-4 space-y-2">
            <p className="text-sm text-emerald-600 font-medium">
              거래내역 {state.rowCount.toLocaleString('ko-KR')}건을 확인했습니다.
            </p>
            {state.skippedRowCount > 0 && (
              <p className="text-xs text-gray-500">
                형식이 맞지 않아 건너뛴 행 {state.skippedRowCount.toLocaleString('ko-KR')}건
              </p>
            )}
            <Button variant="secondary" onClick={reset}>
              다른 파일 업로드
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
