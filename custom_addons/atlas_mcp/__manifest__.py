{
    'name': 'Atlas MCP Sunucusu',
    'version': '20.0.1.0.0',
    'category': 'Productivity',
    'summary': 'Atlas ERP\'yi Model Context Protocol (MCP) sunucusu olarak açar: yapay zekâ istemcileri (Claude vb.) API anahtarıyla '
               'kullanıcının yetkileri dahilinde veri sorgular (Enterprise ai_mcp eşleniği)',
    'description': """
MCP Sunucusu
============
- Adres: https://<atlas-adresi>/mcp  (MCP Streamable HTTP, JSON-RPC 2.0)
- Kimlik doğrulama: Authorization: Bearer <API anahtarı> (Tercihler › Hesap Güvenliği › API Anahtarları)
- Araçlar: modelleri listele, alanları getir, kayıt ara, kayıt oku, say, grupla (toplam/ortalama);
  isteğe bağlı kayıt oluştur / güncelle (Ayarlar'dan açılır, varsayılan kapalı)
- Her çağrı anahtar sahibinin erişim haklarıyla çalışır; çağrılar günlüğe yazılır
    """,
    'author': 'Atlas',
    'depends': ['atlas_ai'],
    'data': [
        'security/ir.access.csv',
        'views/mcp_views.xml',
    ],
    'installable': True,
    'license': 'LGPL-3',
}
