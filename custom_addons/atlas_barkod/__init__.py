from . import models

# Her ürün seri numarası ve QR etiketiyle izlenir; dökme malzemeler (ilk madde) takipsiz kalır
SERI_TAKIPLI_KATEGORILER = ('atlas_stok.categ_mamul', 'atlas_stok.categ_ticari_mal', 'product.product_category_goods')


def _atlas_barkod_post_init(env):
    for xmlid in SERI_TAKIPLI_KATEGORILER:
        category = env.ref(xmlid, raise_if_not_found=False)
        if category and not category.atlas_varsayilan_takip:
            category.atlas_varsayilan_takip = 'serial'
