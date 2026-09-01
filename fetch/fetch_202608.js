// 取得 202608 (2026-08-01 ~ 2026-08-31) 各客戶原始計費資料。
//
// 用法：
//   1. 瀏覽器登入 https://dashboard.authme.com
//   2. 開 DevTools console，貼上整段執行
//   3. 每個客戶會下載一個 <key>.json，全部放進 data/202608/
//   4. python -m saas_billing.report --month 202608 --data-dir data/202608
//
// TENANTS 裡 tenantId 為 null 的客戶，請先從 Dashboard 的 tenant 選擇器切過去，
// 從網址或 API 呼叫把 tenantId 抄下來填入 —— 不要用猜的，計費查詢打錯 tenant
// 會拿到別的客戶的數字。

const START = '2026-08-01';
const END = '2026-08-31';

const TENANTS = {
  juji: '3a1799d1-fbb1-4c91-351a-edf86d0cb8b7',
  aftee: '3a0f6f28-ab2f-0ac1-abe5-502db51fc790',
  esafe: null,             // 紅陽
  amazingtalker: null,
  xo_dating: null,
  gamania_xchanger: null,
  cashmallow_hk: null,     // 下線中，仍需計算次數
  cashmallow_jp: null,
};

(async () => {
  const token = localStorage.getItem('access_token');
  if (!token) {
    console.error('拿不到 access_token —— 請確認已登入 Dashboard');
    return;
  }

  const download = (name, items) => {
    const blob = new Blob([JSON.stringify(items, null, 2)], { type: 'application/json' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `${name}.json`;
    link.click();
    URL.revokeObjectURL(link.href);
  };

  for (const [key, tenantId] of Object.entries(TENANTS)) {
    if (!tenantId) {
      console.warn(`跳過 ${key}：尚未填入 tenantId`);
      continue;
    }

    // maxResultCount 上限 10000，用 skipCount 翻頁直到取完，
    // 免得用量大的月份被默默截斷。
    const items = [];
    for (let skip = 0; ; skip += 10000) {
      const url = 'https://api.authme.com/api/identity-verification/v1/reports/billing/export'
        + `?startTime=${START}&endTime=${END}&tenantId=${tenantId}`
        + `&skipCount=${skip}&maxResultCount=10000`;
      const resp = await fetch(url, { headers: { Authorization: 'Bearer ' + token } });
      if (!resp.ok) {
        console.error(`${key}: HTTP ${resp.status}`);
        break;
      }
      const data = await resp.json();
      const page = data.items || data.result?.items || [];
      items.push(...page);
      if (page.length < 10000) break;
    }

    console.log(`${key}: ${items.length} 筆`);
    download(key, items);
  }

  console.log('完成。請把下載的 json 放到 data/202608/ 後執行報表腳本。');
})();
