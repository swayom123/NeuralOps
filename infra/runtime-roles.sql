-- Run as the database provisioning administrator after migrations.
-- Roles have NOLOGIN. Grant one role to each externally provisioned LOGIN account.
-- Passwords/certificates must come from the deployment secret store, never this file.
DO $$ DECLARE role_name text; BEGIN
  FOREACH role_name IN ARRAY ARRAY['neuralops_api','neuralops_ingest','neuralops_worker'] LOOP
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname=role_name) THEN
      EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS', role_name);
    END IF;
  END LOOP;
END $$;
GRANT USAGE ON SCHEMA public TO neuralops_api, neuralops_ingest, neuralops_worker;
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
GRANT SELECT ON organizations,memberships,user_sessions,projects,ingestion_credentials,spans,traces,jobs,rules,rule_versions,detections,incidents,hypotheses,evidence_links,incident_notes,slos,slo_snapshots,change_events,datasets,evaluations,remediations,audit_events,expired_traces TO neuralops_api;
GRANT INSERT ON projects,ingestion_credentials,jobs,rules,rule_versions,incident_notes,slos,change_events,datasets,evaluations,remediations,audit_events,user_sessions TO neuralops_api;
GRANT DELETE ON user_sessions,rules,rule_versions,detections,jobs TO neuralops_api;
GRANT UPDATE(retention_days) ON projects TO neuralops_api;
GRANT UPDATE(revoked) ON ingestion_credentials TO neuralops_api;
GRANT UPDATE(name,metric,detector,threshold,sensitivity,ewma_alpha,min_samples,window_minutes,cooldown_minutes,severity,enabled,version,deleted_at) ON rules TO neuralops_api;
GRANT UPDATE(enabled) ON slos TO neuralops_api;
GRANT UPDATE(status,updated_at,timeline) ON incidents TO neuralops_api;
GRANT UPDATE(state) ON remediations TO neuralops_api;
GRANT SELECT ON projects,ingestion_credentials,spans,jobs TO neuralops_ingest;
GRANT INSERT ON spans,jobs TO neuralops_ingest;
GRANT UPDATE(end_ns,status,attributes,links,redacted_count) ON spans TO neuralops_ingest;
GRANT UPDATE(rate_minute,rate_count) ON ingestion_credentials TO neuralops_ingest;
GRANT SELECT ON projects,spans,traces,jobs,rules,rule_versions,detections,incidents,hypotheses,evidence_links,incident_notes,slos,slo_snapshots,change_events,datasets,evaluations,expired_traces,rate_buckets TO neuralops_worker;
GRANT INSERT ON traces,jobs,detections,incidents,hypotheses,evidence_links,slo_snapshots,audit_events,expired_traces TO neuralops_worker;
GRANT UPDATE ON traces,jobs,detections,incidents,slo_snapshots,evaluations TO neuralops_worker;
GRANT UPDATE(state,last_observed,last_fired_at) ON rules TO neuralops_worker;
GRANT SELECT(expires_at) ON user_sessions TO neuralops_worker;
GRANT DELETE ON spans,traces,user_sessions,rate_buckets,jobs TO neuralops_worker;
GRANT DELETE ON hypotheses,evidence_links TO neuralops_worker;
GRANT SELECT,INSERT,UPDATE ON rate_buckets TO neuralops_api,neuralops_ingest,neuralops_worker;
DO $$ DECLARE table_name text; BEGIN
  FOREACH table_name IN ARRAY ARRAY['projects','ingestion_credentials','spans','traces','jobs','rules','rule_versions','detections','incidents','hypotheses','evidence_links','incident_notes','slos','slo_snapshots','change_events','datasets','evaluations','remediations','audit_events','expired_traces'] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS api_tenant ON %I', table_name);
    EXECUTE format('CREATE POLICY api_tenant ON %I FOR ALL TO neuralops_api USING (organization_id=current_setting(''neuralops.organization_id'',true)) WITH CHECK (organization_id=current_setting(''neuralops.organization_id'',true))',table_name);
    EXECUTE format('DROP POLICY IF EXISTS worker_control ON %I', table_name);
    EXECUTE format('CREATE POLICY worker_control ON %I FOR ALL TO neuralops_worker USING (true) WITH CHECK (true)',table_name);
    IF table_name IN ('projects','spans','jobs') THEN
      EXECUTE format('DROP POLICY IF EXISTS ingest_tenant ON %I', table_name);
      EXECUTE format('CREATE POLICY ingest_tenant ON %I FOR ALL TO neuralops_ingest USING (organization_id=current_setting(''neuralops.organization_id'',true)) WITH CHECK (organization_id=current_setting(''neuralops.organization_id'',true))',table_name);
    END IF;
  END LOOP;
END $$;
DROP POLICY IF EXISTS ingestion_credential_lookup ON ingestion_credentials;
CREATE POLICY ingestion_credential_lookup ON ingestion_credentials FOR ALL TO neuralops_ingest USING (true) WITH CHECK (true);
