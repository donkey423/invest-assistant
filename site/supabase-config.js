// 「我的資產」雲端模式的設定。兩個都空白＝只讀自己電腦上的 data/private/holdings.json。
// 這裡只放公開金鑰（publishable key，sb_publishable_ 開頭；或舊式 anon key），放在公開網站是安全的：
// 資料靠資料庫的 Row Level Security 保護。絕對不要把 secret／service_role 金鑰放在這裡。
window.SUPABASE_CONFIG = {
  url: "https://xpwucjblikcyvxjilkna.supabase.co",
  key: "sb_publishable_zelt3y4wwzk4mFCKD9fQWw_qeMHzSIz",
};
