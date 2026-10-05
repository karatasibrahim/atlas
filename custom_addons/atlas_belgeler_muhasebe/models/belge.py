import base64

from odoo import api, models
from odoo.exceptions import UserError


class AtlasBelgeBagla(models.TransientModel):
    _inherit = 'atlas.belge.bagla'

    @api.model
    def _bagli_modeller(self):
        return super()._bagli_modeller() + ['account.move', 'account.payment']


class AtlasBelge(models.Model):
    _inherit = 'atlas.belge'

    def _belge_fis(self, tur):
        self._bagli_degil()
        Move = self.env['account.move']
        fisler = Move
        for belge in self:
            vals = {'move_type': tur}
            if tur == 'entry':
                vals['ref'] = belge.name
            elif belge.partner_id:
                vals['partner_id'] = belge.partner_id.id
            fis = Move.create(vals)
            belge._kayda_ekle(fis)
            if hasattr(fis, '_atlas_belgeden_doldur'):  # atlas_ai kuruluysa belgeden okuma
                fis._atlas_belgeden_doldur()
            fisler |= fis
        return self._kayit_ac(fisler, self.env._('Belgeden oluşturulan kayıtlar'))

    def action_belge_tedarikci_faturasi(self):
        return self._belge_fis('in_invoice')

    def action_belge_tedarikci_iadesi(self):
        return self._belge_fis('in_refund')

    def action_belge_musteri_faturasi(self):
        return self._belge_fis('out_invoice')

    def action_belge_musteri_iadesi(self):
        return self._belge_fis('out_refund')

    def action_belge_mahsup(self):
        return self._belge_fis('entry')

    def action_belge_ekstre(self):
        self.ensure_one()
        if not (self.dosya_adi or '').lower().endswith(('.xlsx', '.xlsm', '.csv', '.xml', '.ofx', '.sta', '.mt940', '.940', '.txt')):
            raise UserError(self.env._('Banka ekstresi olarak Excel, CSV, CAMT.053, OFX ya da MT940 dosyası aktarılabilir.'))
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.banka.ekstre.import', 'view_mode': 'form', 'target': 'new',
                'name': self.env._('Banka Ekstresi Aktar'),
                'context': {'default_file': base64.b64encode(self.dosya.content).decode(), 'default_filename': self.dosya_adi}}
