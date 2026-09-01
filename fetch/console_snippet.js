// 在「已經登入 dashboard.authme.com 的瀏覽器」F12 console 貼上執行。
// 借用你當下的登入狀態抓資料，不需要帳密，也不需要手動填 tenant ID。
// 每個租戶會下載一個 <tenant>.json，全部丟給 Claude 即可。

const MONTH = '202608';   // 要出的月份，改這裡就好

(async () => {
  const token = localStorage.getItem('access_token');
  if (!token) return console.error('拿不到 access_token — 請先登入 dashboard 再執行');

  const API = 'https://api.authme.com';
  const auth = { Authorization: 'Bearer ' + token };
  const year = +MONTH.slice(0, 4), mon = +MONTH.slice(4);
  const start = `${year}-${String(mon).padStart(2, '0')}-01`;
  const end = `${year}-${String(mon).padStart(2, '0')}-${new Date(year, mon, 0).getDate()}`;
  console.log(`區間 ${start} ~ ${end}`);

  // 先找租戶清單。不同版本的後台端點不一樣，逐一試，找到就用。
  const CANDIDATES = [
    '/api/saas/tenants?MaxResultCount=200',
    '/api/multi-tenancy/tenants?MaxResultCount=200',
    '/api/identity-verification/v1/reports/billing/tenants',
  ];
  let tenants = null;
  for (const path of CANDIDATES) {
    try {
      const resp = await fetch(API + path, { headers: auth });
      if (!resp.ok) { console.log(`  ${path} -> HTTP ${resp.status}`); continue; }
      const data = await resp.json();
      const list = data.items || data.result?.items || (Array.isArray(data) ? data : null);
      if (list?.length) { tenants = list; console.log(`✓ 租戶清單來自 ${path}（${list.length} 個）`); break; }
    } catch (e) { console.log(`  ${path} -> ${e.message}`); }
  }

  if (!tenants) {
    console.error('自動找不到租戶清單。請改用後台「計費報表」頁面右側的「匯出」下載 CSV，'
                + '或把租戶下拉選單裡的 tenantId 貼給 Claude。');
    return;
  }

  const download = (name, items) => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(items, null, 2)],
                                             { type: 'application/json' }));
    const a = document.createElement('a');
    a.href = url; a.download = `${name}.json`; a.click();
    URL.revokeObjectURL(url);
  };

  const PAGE = 10000;
  for (const tenant of tenants) {
    const id = tenant.id || tenant.tenantId;
    const name = (tenant.name || tenant.tenantName || id).replace(/[^\w.-]/g, '_');
    const items = [];
    // 翻頁到取完，避免用量大的月份被 maxResultCount 默默截斷
    for (;;) {
      const q = new URLSearchParams({ startTime: start, endTime: end, tenantId: id,
                                      skipCount: items.length, maxResultCount: PAGE });
      const resp = await fetch(
        `${API}/api/identity-verification/v1/reports/billing/export?${q}`, { headers: auth });
      if (!resp.ok) { console.error(`${name}: HTTP ${resp.status}`); break; }
      const data = await resp.json();
      const page = data.items || data.result?.items || [];
      items.push(...page);
      if (page.length < PAGE) break;
    }
    console.log(`${name}: ${items.length} 筆`);
    if (items.length) download(name, items);
  }
  console.log('完成 — 把下載的 json 全部丟給 Claude。');
})();
