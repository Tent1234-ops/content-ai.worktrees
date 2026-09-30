from pathlib import Path
import re

path = Path(r"z:/content-ai.worktrees/agents-content-analysis-recommendation-system/docs/api_curl_proof_of_work.sh")
text = path.read_text(encoding="utf-8-sig")
text = text.replace('Authorization: ******', 'Authorization: Bearer ${ACCESS_TOKEN}')
text = re.sub(r'(curl -s -X GET "\$\{BASE_URL\}/admin/settings" \\\n    -H "Authorization: Bearer \$\{ACCESS_TOKEN\}" \\\n    -H "Accept: application/json")', lambda m: m.group(1).replace('${ACCESS_TOKEN}', '${ADMIN_TOKEN}'), text)
text = re.sub(r'(curl -s -X PUT "\$\{BASE_URL\}/admin/settings" \\\n    -H "Authorization: Bearer \$\{ACCESS_TOKEN\}" \\\n    -H "Content-Type: application/json")', lambda m: m.group(1).replace('${ACCESS_TOKEN}', '${ADMIN_TOKEN}'), text)
text = re.sub(r'(curl -s -X GET "\$\{BASE_URL\}/admin/reports/overview" \\\n    -H "Authorization: Bearer \$\{ACCESS_TOKEN\}" \\\n    -H "Accept: application/json")', lambda m: m.group(1).replace('${ACCESS_TOKEN}', '${ADMIN_TOKEN}'), text)
path.write_text(text, encoding='utf-8')
