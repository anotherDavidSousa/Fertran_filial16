# Corrige a sequência do ID de core_motorista no PostgreSQL.
# Erro: duplicate key value violates unique constraint "core_motorista_pkey"
# Causa: sequência dessincronizada (ex.: import com IDs explícitos).
# Ajusta a sequência para o próximo valor ser MAX(id)+1.

from django.db import migrations


def fix_motorista_sequence(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("""
            SELECT setval(
                pg_get_serial_sequence('core_motorista', 'id'),
                COALESCE((SELECT MAX(id) FROM core_motorista), 1)
            );
        """)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0004_motorista_documento_arquivo_optional'),
    ]

    operations = [
        migrations.RunPython(fix_motorista_sequence, noop),
    ]
