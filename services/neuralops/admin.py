"""Out-of-band deployment administration. Run only with operator-controlled database access."""

import argparse

from sqlalchemy import select

from .db import SessionLocal, audit
from .maintenance import retain_project
from .models import Membership, Organization, Project
from .schemas import ProjectInput


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    provision = commands.add_parser(
        "provision", help="Provision an OIDC subject; no passwords or tokens accepted."
    )
    provision.add_argument("--org-slug", required=True)
    provision.add_argument("--org-name", required=True)
    provision.add_argument("--subject", required=True)
    provision.add_argument("--name", required=True)
    provision.add_argument(
        "--role", choices=["admin", "viewer", "developer", "operator", "approver"], required=True
    )
    provision.add_argument("--project-id", action="append", default=[])
    retain = commands.add_parser("retain", help="Apply a project retention policy in bounded batches.")
    retain.add_argument("--project-id", required=True)
    args = parser.parse_args()
    with SessionLocal.begin() as db:
        if args.command == "retain":
            project = db.get(Project, args.project_id)
            if not project:
                parser.error("Project not found.")
            count = retain_project(db, project)
            print(f"Expired {count} traces; rerun until zero to drain a large backlog.")
            return
        ProjectInput(name=args.org_name, slug=args.org_slug)
        if not 1 <= len(args.name) <= 100 or not 1 <= len(args.subject) <= 255:
            parser.error("Identity name or subject length is invalid.")
        org = db.scalar(select(Organization).where(Organization.slug == args.org_slug))
        if not org:
            org = Organization(name=args.org_name, slug=args.org_slug)
            db.add(org)
            db.flush()
        members = db.scalars(select(Membership).where(Membership.subject == args.subject)).all()
        if any(m.organization_id != org.id for m in members):
            parser.error("Multi-organization identity selection is not yet supported.")
        member = members[0] if members else Membership(organization_id=org.id, subject=args.subject)
        for identifier in args.project_id:
            project = db.get(Project, identifier)
            if not project or project.organization_id != org.id:
                parser.error("Project scope does not belong to the organization.")
        if args.role != "admin" and not args.project_id:
            parser.error("Non-admin memberships require explicit project access.")
        member.role, member.name, member.project_ids = args.role, args.name, args.project_id
        db.add(member)
        db.flush()
        audit(db, org.id, "deployment-administrator", "membership.provisioned", member.id)
        print(f"Provisioned membership {member.id}; existing sessions observe role changes immediately.")


if __name__ == "__main__":
    main()
