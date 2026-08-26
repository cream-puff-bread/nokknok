// 거래내역 업로드 API는 아직 없다(백엔드 adapter/file_provider.py는 있지만
// 이를 받는 엔드포인트가 api/ 에 없음). 실제 엔드포인트가 생기면 이 함수
// 내부만 apiPost 같은 실제 호출로 바꾸면 된다 — 반환 타입(UploadOutcome)과
// 실패 시 ApiRequestError를 던지는 규약은 그대로 유지한다.
//
// 완전히 가짜 데이터를 만드는 대신 브라우저에서 실제로 파일을 읽어 파싱해,
// 업로드 화면의 로딩·오류·빈 상태가 실제로 일어날 수 있는 조건에서
// 동작하는지 보여준다.
//   - 오류: 파일이 UTF-8로 디코딩되지 않음(예: 확장자만 바꾼 바이너리 파일).
//     adapter/file_provider.py의 DataSourceError("파일 인코딩을 판별할 수
//     없습니다")에 대응하는 상황이다.
//
//     ⚠ 이 목은 실제보다 엄격하다 — CP949 파일이 여기서는 오류로 뜨지만
//     실제 엔드포인트에서는 정상 처리된다. 아래 TextDecoder 주석 참조.
//   - 빈 상태: 헤더 뿐이거나 유효한 데이터 행이 하나도 없음.
//     adapter/file_provider.py의 DataSourceError("읽을 수 있는 거래 내역이
//     없습니다")에 대응한다.
import { ApiRequestError } from './client';

export interface UploadSuccess {
  status: 'success';
  rowCount: number;
  skippedRowCount: number;
}

export interface UploadEmpty {
  status: 'empty';
}

export type UploadOutcome = UploadSuccess | UploadEmpty;

const MOCK_DELAY_MS = 700;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function detectDelimiter(fileName: string): string {
  return fileName.toLowerCase().endsWith('.tsv') ? '\t' : ',';
}

export async function mockUploadTransactions(file: File): Promise<UploadOutcome> {
  await sleep(MOCK_DELAY_MS);

  let text: string;
  try {
    // fatal: true 로 둬야 잘못된 인코딩(예: 확장자만 바꾼 바이너리 파일)이
    // 조용히 대체 문자로 넘어가지 않고 실제로 오류로 드러난다.
    //
    // 목이 실제보다 엄격한 지점이 여기다: 실제 backend/src/adapter/
    // file_provider.py._parse()는 UTF-8(BOM 포함)이 실패하면 CP949로 한 번
    // 더 시도한다 — 국내 카드사 명세서가 CP949로 내려오는 경우가 많아서다.
    // 이 목은 UTF-8만 시도하므로, 실제로는 정상 처리될 CP949 파일도 화면에는
    // 오류로 뜬다. 업로드 엔드포인트를 실제로 붙이면 이 차이는 저절로
    // 사라지므로, 그때 이 문단(과 위 파일 상단의 ⚠ 표시)도 함께 지운다 —
    // 실제 호출로 바뀌면 인코딩 처리는 서버 책임이라 여기 남겨둘 이유가
    // 없다.
    const buffer = await file.arrayBuffer();
    text = new TextDecoder('utf-8', { fatal: true }).decode(buffer);
  } catch {
    throw new ApiRequestError(
      'INTERNAL_ERROR',
      '파일을 읽을 수 없습니다. 인코딩을 확인해 주세요.',
    );
  }

  const delimiter = detectDelimiter(file.name);
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);

  if (lines.length <= 1) {
    // 헤더만 있거나 완전히 빈 파일.
    return { status: 'empty' };
  }

  const columnCount = lines[0].split(delimiter).length;
  const dataLines = lines.slice(1);
  const validRows = dataLines.filter(
    (line) => line.split(delimiter).length === columnCount,
  );

  if (validRows.length === 0) {
    return { status: 'empty' };
  }

  return {
    status: 'success',
    rowCount: validRows.length,
    skippedRowCount: dataLines.length - validRows.length,
  };
}
