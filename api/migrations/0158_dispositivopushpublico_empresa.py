import unicodedata

from django.db import migrations, models
import django.db.models.deletion


STATE_ALIASES = {
    "RJ": "Rio de Janeiro",
    "SP": "São Paulo",
    "MG": "Minas Gerais",
    "BA": "Bahia",
    "PR": "Parana",
    "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina",
    "GO": "Goias",
    "DF": "Distrito Federal",
    "ES": "Espirito Santo",
    "PE": "Pernambuco",
    "CE": "Ceara",
    "AM": "Amazonas",
}


def _normalize_text(value):
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    return unicodedata.normalize("NFKD", raw).encode("ascii", "ignore").decode("ascii")


_STATE_NAME_TO_UF = {_normalize_text(nome): uf for uf, nome in STATE_ALIASES.items()}


def _to_uf(value):
    raw = (value or "").strip()
    if not raw:
        return ""
    if len(raw) == 2:
        return raw.upper()
    return _STATE_NAME_TO_UF.get(_normalize_text(raw), "")


def backfill_empresa_por_geo(apps, schema_editor):
    """
    Mapeia dispositivos de push legados (cadastrados sem tenant) para a
    Empresa (governo) cuja cidade/uf coincide, só quando o match é único —
    ambiguidade ou ausência de município cliente correspondente deixa o
    device com empresa=NULL, para revisão manual, evitando atribuir um
    dispositivo ao município errado.
    """
    DispositivoPushPublico = apps.get_model("api", "DispositivoPushPublico")
    Empresa = apps.get_model("api", "Empresa")

    candidatos = [
        (e, _normalize_text(e.cidade), _normalize_text(e.uf))
        for e in Empresa.objects.filter(
            tipo_conta="governo", acesso_governo=True, ativo=True
        ).exclude(cidade="")
    ]
    if not candidatos:
        return

    devices = (
        DispositivoPushPublico.objects.filter(empresa__isnull=True)
        .exclude(cidade__isnull=True)
        .exclude(cidade="")
    )
    for device in devices.iterator():
        cidade_norm = _normalize_text(device.cidade)
        if not cidade_norm:
            continue
        uf_norm = _normalize_text(_to_uf(device.estado))
        encontrados = [
            e for e, c, u in candidatos
            if c == cidade_norm and (not uf_norm or u == uf_norm)
        ]
        if len(encontrados) == 1:
            device.empresa = encontrados[0]
            device.save(update_fields=["empresa"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0157_merge_20260721_1800'),
    ]

    operations = [
        migrations.AddField(
            model_name='dispositivopushpublico',
            name='empresa',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='dispositivos_push_publico', to='api.empresa'),
        ),
        migrations.AddIndex(
            model_name='dispositivopushpublico',
            index=models.Index(fields=['empresa', 'ativo'], name='api_disposi_empresa_29eb6c_idx'),
        ),
        migrations.RunPython(backfill_empresa_por_geo, noop_reverse),
    ]
