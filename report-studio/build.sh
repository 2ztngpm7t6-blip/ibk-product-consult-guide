#!/bin/sh
# data/products.json과 로고(assets/logo.b64)를 template.html에 넣어 파일 하나짜리 보고서 생성기를 만든다.
# 상품 정보를 고친 뒤 다시 실행: sh report-studio/build.sh
cd "$(dirname "$0")/.."
LOGO_COLOR=$(sed -n 1p report-studio/assets/logo.b64)
LOGO_WHITE=$(sed -n 2p report-studio/assets/logo.b64)
awk -v c="$LOGO_COLOR" -v w="$LOGO_WHITE" '
  /\/\*__DATA__\*\// { while ((getline line < "data/products.json") > 0) print line; next }
  { gsub(/__LOGO_COLOR__/, c); gsub(/__LOGO_WHITE__/, w); print }
' report-studio/template.html > "IBK_상품상담가이드.html"
echo "built: IBK_상품상담가이드.html"
