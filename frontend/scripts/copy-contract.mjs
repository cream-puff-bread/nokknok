// contracts/types.ts 를 src/types/contract.ts 로 복사한다.
//
// package.json 에 `cp ../contracts/types.ts ...` 를 직접 적으면 npm 이
// 스크립트를 cmd.exe 로 실행하는 Windows 에서만 깨진다. 팀원 중 한 명의
// 빌드만 실패하는 종류의 문제라 발견이 늦으므로, OS 차이가 없는 Node 로 복사한다.
//
// 사본은 커밋하지 않는다(.gitignore). 원본은 항상 contracts/types.ts 하나뿐이며
// 사본을 직접 수정하면 다음 실행에서 그대로 덮어써진다.

import { copyFileSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, '..', '..', 'contracts', 'types.ts');
const dest = resolve(here, '..', 'src', 'types', 'contract.ts');

if (!existsSync(source)) {
  console.error(`계약 파일을 찾을 수 없습니다: ${source}`);
  process.exit(1);
}

mkdirSync(dirname(dest), { recursive: true });
copyFileSync(source, dest);
console.log('contracts/types.ts -> frontend/src/types/contract.ts');
