from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command


class AtlasOdemeTalimatEkle(models.TransientModel):
    _name = 'atlas.odeme.talimat.ekle'
    _description = 'Faturaları Ödeme Talimatına Ekle'

    move_ids = fields.Many2many('account.move', string='Faturalar', required=True)
    talimat_id = fields.Many2one('atlas.odeme.talimat', string='Mevcut Talimat', domain="[('durum', '=', 'taslak')]",
                                 help='Boşsa yeni talimat açılır.')
    journal_id = fields.Many2one('account.journal', string='Banka', domain="[('type', '=', 'bank')]",
                                 default=lambda self: self.env['account.journal'].search(
                                     [('type', '=', 'bank'), ('company_id', '=', self.env.company.id)], limit=1))
    tarih = fields.Date(string='Ödeme Tarihi', default=fields.Date.context_today)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'account.move' and self.env.context.get('active_ids'):
            res['move_ids'] = [Command.set(self.env.context['active_ids'])]
        return res

    def action_ekle(self):
        self.ensure_one()
        faturalar = self.move_ids.filtered(lambda m: m.move_type == 'in_invoice' and m.state == 'posted'
                                           and m.payment_state in ('not_paid', 'partial'))
        if not faturalar:
            raise UserError(self.env._('Seçilenler arasında ödenmemiş onaylı alış faturası yok.'))
        if len(faturalar.company_id) > 1:
            raise UserError(self.env._('Faturalar tek şirkete ait olmalı.'))
        talimat = self.talimat_id
        if not talimat:
            if not self.journal_id:
                raise UserError(self.env._('Banka seçin.'))
            talimat = self.env['atlas.odeme.talimat'].create({'journal_id': self.journal_id.id, 'tarih': self.tarih,
                                                             'company_id': faturalar.company_id.id})
        mevcut = talimat.satir_ids.move_ids
        for partner, moves in faturalar.grouped('commercial_partner_id').items():
            moves -= mevcut
            if not moves:
                continue
            satir = talimat.satir_ids.filtered(lambda s: s.commercial_partner_id == partner and s.move_ids)[:1]
            tutar = sum(moves.mapped('amount_residual'))
            if satir:
                satir.write({'move_ids': [Command.link(m.id) for m in moves], 'tutar': satir.tutar + tutar})
            else:
                self.env['atlas.odeme.talimat.satir'].create({
                    'talimat_id': talimat.id, 'partner_id': partner.id, 'move_ids': [Command.set(moves.ids)], 'tutar': tutar,
                    'aciklama': ', '.join(moves.mapped(lambda m: m.ref or m.name))[:140]})
        return {'type': 'ir.actions.act_window', 'res_model': 'atlas.odeme.talimat', 'res_id': talimat.id, 'view_mode': 'form'}
