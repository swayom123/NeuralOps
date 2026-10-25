"""Enforce immutable audit, dataset and rule-version records in PostgreSQL."""

from alembic import op

revision = "002_immutability"
down_revision = "378171763669"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION neuralops_immutable_record() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'IMMUTABLE_RECORD' USING ERRCODE = '23514'; END; $$""")
    for table in ("audit_events", "datasets", "rule_versions"):
        op.execute(f"""CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE ON {table}
                       FOR EACH ROW EXECUTE FUNCTION neuralops_immutable_record()""")
    op.execute("""CREATE FUNCTION neuralops_immutable_manifest() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF NEW.manifest::text <> OLD.manifest::text OR NEW.manifest_hash <> OLD.manifest_hash
         OR NEW.proposer <> OLD.proposer OR NEW.expires_at <> OLD.expires_at
         OR NEW.incident_id <> OLD.incident_id OR NEW.project_id <> OLD.project_id
         OR NEW.organization_id <> OLD.organization_id THEN
         RAISE EXCEPTION 'IMMUTABLE_MANIFEST' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END; $$""")
    op.execute("""CREATE TRIGGER remediation_manifest_immutable BEFORE UPDATE ON remediations
                  FOR EACH ROW EXECUTE FUNCTION neuralops_immutable_manifest()""")
    # Backfill v1 snapshots for rules created before version history was introduced.
    op.execute("""INSERT INTO rule_versions (id, organization_id, project_id, rule_id, version, manifest, created_at)
                  SELECT gen_random_uuid()::text, organization_id, project_id, id, version,
                         json_build_object('name',name,'metric',metric,'threshold',threshold,'min_samples',min_samples,
                                           'window_minutes',window_minutes,'cooldown_minutes',cooldown_minutes,
                                           'severity',severity,'enabled',enabled), now()
                  FROM rules ON CONFLICT (rule_id,version) DO NOTHING""")


def downgrade():
    op.execute("DROP TRIGGER remediation_manifest_immutable ON remediations")
    op.execute("DROP FUNCTION neuralops_immutable_manifest()")
    for table in ("audit_events", "datasets", "rule_versions"):
        op.execute(f"DROP TRIGGER {table}_immutable ON {table}")
    op.execute("DROP FUNCTION neuralops_immutable_record()")
