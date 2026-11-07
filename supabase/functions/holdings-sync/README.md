# holdings-sync（Supabase Edge Function）

讓 GitHub Actions 的 `holdings.yml` 不需要任何密鑰就能讀持股、寫回計算結果。

- 驗證：GitHub Actions 發的 OIDC 身分證明（GitHub 簽章的 JWT），只接受 `donkey423/invest-assistant` main 分支上的 `.github/workflows/holdings.yml`，audience 為 `invest-assistant-holdings`。
- 因為自己驗證身分，部署時 `verify_jwt` 設為 false。
- 通過驗證後才用 Supabase 內建的 service role 讀寫 `holdings`、`transactions`、`holdings_reports`。

已部署到專案 xpwucjblikcyvxjilkna。原始碼見 index.ts。
