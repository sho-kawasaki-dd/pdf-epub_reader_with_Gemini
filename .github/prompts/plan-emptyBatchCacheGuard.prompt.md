## Plan: Empty Batch Cache Guard

browser-extension の batch 全解除を first-class state として扱い、empty batch では article cache auto-create を起こさないようにする。同時に clear-all command と popup debug cache management を追加し、browser_api には browser-extension 所有 cache の list/delete 導線を足す。既存の close overlay と active cache delete は別責務のまま維持する。

**Steps**
1. Phase 1: Empty batch state を定義する。c:\Users\tohbo\python_programs\gem-read\browser-extension\src\background\usecases\updateSelectionSession.ts で「items は空だが overlay context と article cache state は保持する」session 更新経路を追加する。最後の 1 件削除時もこの経路に統一し、clearAnalysisSession(tabId) は overlay close 専用に残す。
2. Phase 1: clear-all 用 message / command contract を追加する。c:\Users\tohbo\python_programs\gem-read\browser-extension\src\shared\contracts\messages.ts に clear-all runtime message を追加し、c:\Users\tohbo\python_programs\gem-read\browser-extension\src\shared\config\phase0.ts と c:\Users\tohbo\python_programs\gem-read\browser-extension\manifest.json に browser command id を追加する。command は Ctrl+Shift+0 / Command+Shift+0 を割り当てる。
3. Phase 1: background command / message handler を実装する。c:\Users\tohbo\python_programs\gem-read\browser-extension\src\background\entry.ts で new command と clear-all message を受け、tab-scoped session を empty batch state に更新して overlay を full panel のまま再描画する。active article cache は削除しない。*depends on 1,2*
4. Phase 1: overlay keyboard support を追加する。c:\Users\tohbo\python_programs\gem-read\browser-extension\src\content\overlay\renderOverlay.ts の keyboard handler に Alt+Backspace を追加し、editable target 上では発火させず、runtime clear-all message を background へ送る。overlay hint 文言も更新する。*parallel with 3 after 2*
5. Phase 2: empty batch auto-create guard を実装する。c:\Users\tohbo\python_programs\gem-read\browser-extension\src\background\usecases\openOverlaySession.ts と c:\Users\tohbo\python_programs\gem-read\browser-extension\src\background\usecases\runSelectionAnalysis.ts で syncArticleCacheState() に渡す allowAutoCreate を batch items の有無で制御する。batch が空のときだけ auto-create を抑止し、選択を持つ通常 analyze / rerun は従来どおり維持する。*depends on 1*
6. Phase 2: popup debug cache list API を追加する。c:\Users\tohbo\python_programs\gem-read\src\browser_api\adapters\ai_gateway.py、c:\Users\tohbo\python_programs\gem-read\src\browser_api\application\dto.py、c:\Users\tohbo\python_programs\gem-read\src\browser_api\application\services\analyze_service.py、c:\Users\tohbo\python_programs\gem-read\src\browser_api\api\schemas\cache.py、c:\Users\tohbo\python_programs\gem-read\src\browser_api\api\routers\cache.py に browser-extension prefix 専用の cache list endpoint を追加する。prefix filtering は application service で行い、popup には browser-extension 所有 cache のみ返す。*parallel with 5*
7. Phase 2: popup debug UI と delete action を実装する。c:\Users\tohbo\python_programs\gem-read\browser-extension\src\shared\gateways\localApiGateway.ts に list caches client を追加し、c:\Users\tohbo\python_programs\gem-read\browser-extension\src\popup\ui\renderPopup.ts に常時表示だが折りたたみの debug section を追加する。一覧は browser-extension cache 全件を表示し、各行に delete action を持たせる。confirm dialog は入れず、操作結果は popup message line に出す。*depends on 6*
8. Phase 3: unit tests と docs を更新する。browser-extension では openOverlaySession / runSelectionAnalysis / clear-all command / overlay keyboard / popup debug UI の unit tests を追加・更新する。browser_api では cache list router/service tests を追加する。docs は user operations と developer testing / runtime flow を今回の仕様に合わせて更新する。*depends on 3,4,5,6,7*

**Relevant files**
- c:\Users\tohbo\python_programs\gem-read\browser-extension\src\background\usecases\updateSelectionSession.ts — empty batch state を組み立てる中心。最後の 1 件削除と clear-all を統一する。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\src\background\entry.ts — browser command, runtime message, overlay rerender の集約点。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\src\background\usecases\openOverlaySession.ts — reopen 時の article cache sync と allowAutoCreate 条件。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\src\background\usecases\runSelectionAnalysis.ts — fresh analyze / rerun 時の article cache sync と allowAutoCreate 条件。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\src\content\overlay\renderOverlay.ts — Alt+Backspace、hint 文言、empty batch 表示。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\src\shared\contracts\messages.ts — clear-all message と popup debug 用 response shape の共有 contract。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\src\shared\config\phase0.ts — clear-all command id 追加。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\manifest.json — Ctrl+Shift+0 / Command+Shift+0 command を定義。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\src\shared\gateways\localApiGateway.ts — list caches / delete cache client を popup から利用する。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\src\popup\ui\renderPopup.ts — foldable debug section、一覧表示、delete action、結果メッセージ。
- c:\Users\tohbo\python_programs\gem-read\src\browser_api\adapters\ai_gateway.py — AIModel.list_caches() bridge を追加。
- c:\Users\tohbo\python_programs\gem-read\src\browser_api\application\services\analyze_service.py — browser-extension prefix filtering と response shaping。
- c:\Users\tohbo\python_programs\gem-read\src\browser_api\application\dto.py — cache list result DTO。
- c:\Users\tohbo\python_programs\gem-read\src\browser_api\api\schemas\cache.py — cache list response schema。
- c:\Users\tohbo\python_programs\gem-read\src\browser_api\api\routers\cache.py — GET cache list endpoint。
- c:\Users\tohbo\python_programs\gem-read\src\pdf_epub_reader\models\ai_model.py — list_caches() が現在 pdf-reader prefix のみを返すことの確認元。必要なら filtering responsibility をここではなく browser_api service 側に維持する。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\__tests__\unit\background\openOverlaySession.test.ts — empty batch reopen の仕様変更を反映。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\__tests__\unit\background\runSelectionAnalysis.test.ts — empty batch guard と auto-create 維持ケースを検証。
- c:\Users\tohbo\python_programs\gem-read\browser-extension\__tests__\unit\content\renderOverlay.test.ts — Alt+Backspace と hint 文言を検証。
- c:\Users\tohbo\python_programs\gem-read\tests\test_browser_api\test_api — cache list endpoint tests を追加。
- c:\Users\tohbo\python_programs\gem-read\docs\user\operations.md — clear-all shortcut と empty batch reopen behavior を更新。
- c:\Users\tohbo\python_programs\gem-read\docs\developer\testing.md — manual / automated verification expectations を更新。

**Verification**
1. browser-extension unit tests で以下を追加・更新する: empty batch で overlay reopen しても auto-create されない、選択ありでは従来どおり auto-create 候補判定される、Ctrl+Shift+0 command で batch が空になる、Alt+Backspace が editable target 以外でだけ clear-all を送る、popup debug section が list/delete を反映する。
2. browser_api tests で GET /cache/list が browser-extension prefix の cache のみ返すこと、空配列、API key missing、upstream API error を検証する。
3. 手動確認: batch を作成して article cache が active になった後、全解除して overlay を reopen しても new cache create が走らないことを logs / mock requests で確認する。
4. 手動確認: 全解除後でも full overlay が維持され、article context と既存 active cache 状態が見えること、Delete Cache は引き続き別操作として機能することを確認する。
5. 手動確認: popup debug section で browser-extension cache 一覧が取れ、一覧から delete した cache が消えること、結果メッセージが表示されることを確認する。

**Decisions**
- empty batch 後は full overlay を維持し、batch だけ空にする。
- auto-create 抑止は batch が空のときだけ適用する。
- clear-all は active article cache を削除しない。Delete Cache を明示的な別操作として残す。
- 最後の 1 件削除も clear-all と同じ empty batch state に揃える。
- clear-all は browser command と overlay keyboard の両方を提供する。browser command は Ctrl+Shift+0 / Command+Shift+0、overlay key は Alt+Backspace。
- debug UI は popup に置き、常時表示だが折りたたみとする。
- debug cache list は browser-extension prefix の cache のみを対象とする。
- debug list から browser-extension cache 全件の個別削除を許可し、確認ダイアログは入れない。
- scope includes: browser-extension behavior change, popup debug UI, browser_api cache list support, tests, docs.
- scope excludes: overlay 内の debug list UI 追加、pdf-reader 側 cache dialog の挙動変更、cache ownership prefix の再設計。