from pathlib import Path
path = Path(r"z:/content-ai.worktrees/agents-content-analysis-recommendation-system/docs/api_curl_proof_of_work.sh")
line = path.read_text(encoding="utf-8-sig").splitlines(keepends=True)[33].strip()
compare = '-H "Authorization: ******" \\'
print('line', repr(line), len(line), [ord(c) for c in line])
print('compare', repr(compare), len(compare), [ord(c) for c in compare])
print('equal', line == compare)
