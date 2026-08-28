# Authorization v2 foundation catalogue

> Foundation artifact: implemented and verified, but not registered in the live application. Live enforcement remains on the legacy engines until the atomic cutover.

## Actions

### `account.mobile_sessions.revoke`

Authorize account.mobile_sessions.revoke.

Resource: `mobile_session`; disclosure: `masked`; audit: `required`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `account.mobile_sessions.view`

Authorize account.mobile_sessions.view.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `account.notifications.update`

Authorize account.notifications.update.

Resource: `user`; disclosure: `masked`; audit: `required`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `account.notifications.view`

Authorize account.notifications.view.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `account.password.change`

Authorize account.password.change.

Resource: `user`; disclosure: `masked`; audit: `required`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `account.profile.update`

Authorize account.profile.update.

Resource: `user`; disclosure: `masked`; audit: `required`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `account.profile.view`

Authorize account.profile.view.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `account.viewer_preferences.manage`

Authorize account.viewer_preferences.manage.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `ad_hoc_task.create`

Authorize ad_hoc_task.create.

Resource: `ad_hoc_task`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `ad_hoc_task.delete`

Authorize ad_hoc_task.delete.

Resource: `ad_hoc_task`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `ad_hoc_task.view`

Authorize ad_hoc_task.view.

Resource: `ad_hoc_task`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=data_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `admin.dashboard.view`

Authorize admin.dashboard.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=local_admin), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `admin.grading_eligibility.manage`

Authorize admin.grading_eligibility.manage.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=data_manager), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `admin.lookup.manage`

Authorize admin.lookup.manage.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `admin.s3.manage`

Authorize admin.s3.manage.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `admin.security.view`

Authorize admin.security.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `admin.system.manage`

Authorize admin.system.manage.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `admin.upload_profiles.manage`

Authorize admin.upload_profiles.manage.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `admin.upload_profiles.update`

Authorize admin.upload_profiles.update.

Resource: `upload_profile`; disclosure: `identifier_in_place`; audit: `optional`.

- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `admin.users.create`

Authorize admin.users.create.

Resource: `user_creation_target`; disclosure: `identifier_in_place`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=user_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `admin.users.manage`

Authorize admin.users.manage.

Resource: `user`; disclosure: `identifier_in_place`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=user_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `admin.users.view`

Authorize admin.users.view.

Resource: `user`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=data_manager,user_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `admin.users.workspace.view`

Authorize admin.users.workspace.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=local_admin), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `analytics.encounters.view`

Authorize analytics.encounters.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=analytics_viewer,collaborator,data_manager,local_admin,ophthalmologist,project_admin,project_pi,site_pi), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `analytics.hospital_dashboard.view`

Authorize analytics.hospital_dashboard.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=analytics_viewer,collaborator,data_manager,local_admin,ophthalmologist,project_admin,project_pi,site_pi), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `analytics.kpi.direct_files.rows`

Authorize analytics.kpi.direct_files.rows.

Resource: `direct_image_upload`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=analytics_viewer,collaborator,data_manager,local_admin,ophthalmologist,project_admin,project_pi,site_pi; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `analytics.kpi.encounter_files.rows`

Authorize analytics.kpi.encounter_files.rows.

Resource: `encounter_file`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=analytics_viewer,collaborator,data_manager,local_admin,ophthalmologist,project_admin,project_pi,site_pi; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `analytics.kpi.view`

Authorize analytics.kpi.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=analytics_viewer,collaborator,data_manager,local_admin,ophthalmologist,project_admin,project_pi,site_pi), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `analytics.upload_stats.view`

Authorize analytics.upload_stats.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=analytics_viewer,collaborator,data_manager,local_admin,ophthalmologist,project_admin,project_pi,site_pi), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `api.lookups.manage`

Authorize api.lookups.manage.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `api.lookups.view`

Authorize api.lookups.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=data_manager,fileUploader,local_admin,ophthalmologist,optometrist), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `api.mobile.session.manage`

Authorize api.mobile.session.manage.

Resource: `mobile_session`; disclosure: `masked`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=user_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `api.ocr.manage`

Authorize api.ocr.manage.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=verifier), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `audit.data_quality.view`

Authorize audit.data_quality.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `auth.login`

Authorize auth.login.

Resource: `public`; disclosure: `masked`; audit: `optional`.

- `public`: PublicRequirement()

### `auth.logout`

Authorize auth.logout.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `auth.mobile.logout`

Authorize auth.mobile.logout.

Resource: `mobile_session`; disclosure: `masked`; audit: `optional`.

- `signed_credential`: SessionChannelRequirement(channels=signed), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=target_active; expected=True), RelationshipRequirement(source=signed_credential; attributes=(); require_subject=False; require_scope=False)

### `auth.mobile.refresh`

Authorize auth.mobile.refresh.

Resource: `mobile_session`; disclosure: `masked`; audit: `optional`.

- `signed_credential`: SessionChannelRequirement(channels=signed), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=target_active; expected=True), RelationshipRequirement(source=signed_credential; attributes=(); require_subject=False; require_scope=False)

### `auth.password_reset.complete`

Authorize auth.password_reset.complete.

Resource: `password_reset_credential`; disclosure: `masked`; audit: `required`.

- `signed_credential`: SessionChannelRequirement(channels=signed), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=target_active; expected=True), RelationshipRequirement(source=signed_credential; attributes=(); require_subject=False; require_scope=False)

### `auth.password_reset.request`

Authorize auth.password_reset.request.

Resource: `public`; disclosure: `masked`; audit: `optional`.

- `public`: PublicRequirement()

### `auth.reauth`

Authorize auth.reauth.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `authorization.catalogue.view`

Authorize authorization.catalogue.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `authorization.grants.manage`

Authorize authorization.grants.manage.

Resource: `grant_target`; disclosure: `masked`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=local_admin,project_admin,project_pi,site_pi,user_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `authorization.grants.view`

Authorize authorization.grants.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=local_admin,project_admin,project_pi,site_pi,user_manager), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `authorization.me.capabilities.view`

Authorize authorization.me.capabilities.view.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `authorization.me.upload_options.view`

Authorize authorization.me.upload_options.view.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `authorization.me.workspaces.view`

Authorize authorization.me.workspaces.view.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `dashboard.view`

Authorize dashboard.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=data_manager,fileUploader,local_admin,ophthalmologist,optometrist), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `dataset.curation.image.update`

Authorize dataset.curation.image.update.

Resource: `image`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=dataset_creator; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `dataset.curation.update`

Authorize dataset.curation.update.

Resource: `dataset`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=dataset_creator; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `dataset.curation.view`

Authorize dataset.curation.view.

Resource: `dataset`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=analytics_viewer,data_exporter,data_manager,dataset_creator,local_admin; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `dataset.delete`

Authorize dataset.delete.

Resource: `dataset`; disclosure: `masked`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=dataset_creator; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `dataset.export.create`

Authorize dataset.export.create.

Resource: `dataset`; disclosure: `masked`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_exporter; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `dataset.export.download`

Authorize dataset.export.download.

Resource: `dataset`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_exporter; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `dataset.export.download_identifiers`

Authorize dataset.export.download_identifiers.

Resource: `dataset`; disclosure: `identifier_release`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_exporter; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `dataset.export.grades`

Authorize dataset.export.grades.

Resource: `dataset`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_exporter; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `dataset.finalize`

Authorize dataset.finalize.

Resource: `dataset`; disclosure: `masked`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=dataset_creator; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `dataset.public_download`

Authorize dataset.public_download.

Resource: `dataset_share`; disclosure: `masked`; audit: `optional`.

- `signed_credential`: SessionChannelRequirement(channels=signed), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=target_active; expected=True), RelationshipRequirement(source=signed_credential; attributes=(); require_subject=False; require_scope=False)

### `dataset.share.manage`

Authorize dataset.share.manage.

Resource: `dataset`; disclosure: `masked`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_exporter; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `docs.api.view`

Authorize docs.api.view.

Resource: `public`; disclosure: `masked`; audit: `optional`.

- `public`: PublicRequirement()

### `glaucoma_ai.result.view`

Authorize glaucoma_ai.result.view.

Resource: `inference_result`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=analytics_viewer,collaborator,data_exporter,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `glaucoma_ai.upload.create`

Authorize glaucoma_ai.upload.create.

Resource: `project_upload_target`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_upload_profile`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=fileUploader,optometrist; allow_system=False), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=admin; allow_system=True), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)

### `glaucoma_ai.workspace.view`

Authorize glaucoma_ai.workspace.view.

Resource: `project`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=analytics_viewer,collaborator,data_exporter,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `grading.arbitrator.submit`

Authorize grading.arbitrator.submit.

Resource: `grading_task`; disclosure: `masked`; audit: `optional`.

- `qualified_slot`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=field_ophthalmologist,ophthalmologist; allow_system=False), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=grading_slot; attributes=(('workflow_accepts', True), ('no_conflict', True), ('no_duplicate', True), ('allocation_enforced', False)); require_subject=True; require_scope=True), RelationshipRequirement(source=grading_slot; attributes=(('workflow_accepts', True), ('no_conflict', True), ('no_duplicate', True), ('allocation_enforced', True)); require_subject=True; require_scope=True), RelationshipRequirement(source=project_allocation; attributes=(); require_subject=True; require_scope=True)

### `grading.grades.view`

Authorize grading.grades.view.

Resource: `grading_task`; disclosure: `masked`; audit: `optional`.

- `participant`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=field_ophthalmologist,ophthalmologist), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=participation; attributes=(); require_subject=True; require_scope=True)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=admin; allow_system=True), BooleanRequirement(fact=exact_resource; expected=True)

### `grading.resident.submit`

Authorize grading.resident.submit.

Resource: `grading_task`; disclosure: `masked`; audit: `optional`.

- `qualified_slot`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=field_ophthalmologist,ophthalmologist; allow_system=False), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=grading_slot; attributes=(('workflow_accepts', True), ('no_conflict', True), ('no_duplicate', True), ('allocation_enforced', False)); require_subject=True; require_scope=True), RelationshipRequirement(source=grading_slot; attributes=(('workflow_accepts', True), ('no_conflict', True), ('no_duplicate', True), ('allocation_enforced', True)); require_subject=True; require_scope=True), RelationshipRequirement(source=project_allocation; attributes=(); require_subject=True; require_scope=True)

### `grading.resident2.submit`

Authorize grading.resident2.submit.

Resource: `grading_task`; disclosure: `masked`; audit: `optional`.

- `qualified_slot`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=field_ophthalmologist,ophthalmologist; allow_system=False), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=grading_slot; attributes=(('workflow_accepts', True), ('no_conflict', True), ('no_duplicate', True), ('allocation_enforced', False)); require_subject=True; require_scope=True), RelationshipRequirement(source=grading_slot; attributes=(('workflow_accepts', True), ('no_conflict', True), ('no_duplicate', True), ('allocation_enforced', True)); require_subject=True; require_scope=True), RelationshipRequirement(source=project_allocation; attributes=(); require_subject=True; require_scope=True)

### `help.view`

Authorize help.view.

Resource: `public`; disclosure: `masked`; audit: `optional`.

- `public`: PublicRequirement()

### `inference.wai.retrospective.run`

Authorize inference.wai.retrospective.run.

Resource: `inference_target`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)
- `stored_automation_rule`: SessionChannelRequirement(channels=automation), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=automation_rule; attributes=(('target_matches', True),); require_subject=False; require_scope=True), BooleanRequirement(fact=domain_valid; expected=True)

### `inference.wai.retry`

Authorize inference.wai.retry.

Resource: `job`; disclosure: `masked`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_manager,local_admin; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)
- `stored_automation_rule`: SessionChannelRequirement(channels=automation), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=automation_rule; attributes=(('target_matches', True),); require_subject=False; require_scope=True), BooleanRequirement(fact=domain_valid; expected=True)

### `inference.wai.rows`

Authorize inference.wai.rows.

Resource: `inference_result`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=data_manager,field_ophthalmologist,field_optometrist,fileUploader,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `inference.wai.run`

Authorize inference.wai.run.

Resource: `inference_target`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=field_ophthalmologist,field_optometrist,optometrist,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)
- `stored_automation_rule`: SessionChannelRequirement(channels=automation), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=automation_rule; attributes=(('target_matches', True),); require_subject=False; require_scope=True), BooleanRequirement(fact=domain_valid; expected=True)

### `inference.wai.summary`

Authorize inference.wai.summary.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=analytics_viewer,collaborator,data_exporter,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `intra_rater.batch.create`

Authorize intra_rater.batch.create.

Resource: `intra_rater_batch`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `intra_rater.batch.view`

Authorize intra_rater.batch.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=data_manager), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `intra_rater.kpi.view`

Authorize intra_rater.kpi.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=data_manager,ophthalmologist), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `intra_rater.task.submit`

Authorize intra_rater.task.submit.

Resource: `intra_rater_task`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=ophthalmologist; allow_system=False)

### `intra_rater.task.view`

Authorize intra_rater.task.view.

Resource: `intra_rater_task`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=data_manager,ophthalmologist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `jobs.regenerate`

Authorize jobs.regenerate.

Resource: `job`; disclosure: `masked`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_exporter,data_manager,dataset_creator,discrepancy_reviewer,fileUploader,local_admin,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `jobs.result.view`

Authorize jobs.result.view.

Resource: `job`; disclosure: `masked`; audit: `optional`.

- `owner`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), AnyRoleRequirement(roles=admin,data_exporter,data_manager,dataset_creator,discrepancy_reviewer,fileUploader,local_admin,optometrist), RelationshipRequirement(source=ownership; attributes=(); require_subject=True; require_scope=False)
- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=data_exporter,data_manager,dataset_creator,discrepancy_reviewer,fileUploader,local_admin,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `jobs.view`

Authorize jobs.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=data_exporter,data_manager,dataset_creator,discrepancy_reviewer,fileUploader,local_admin,optometrist), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `media.image.view`

Authorize media.image.view.

Resource: `image`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=analytics_viewer,collaborator,data_exporter,data_manager,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,fileUploader,local_admin,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)
- `signed_credential`: SessionChannelRequirement(channels=signed), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=target_active; expected=True), RelationshipRequirement(source=signed_credential; attributes=(); require_subject=False; require_scope=False)

### `media.metadata.process`

Authorize media.metadata.process.

Resource: `image`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `media.metadata.raw.read`

Authorize media.metadata.raw.read.

Resource: `image`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=data_manager,fileUploader,local_admin,optometrist,pregraded_uploader,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `media.metadata.read`

Authorize media.metadata.read.

Resource: `image`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=analytics_viewer,collaborator,data_exporter,data_manager,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,fileUploader,local_admin,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `media.ocr_pii.process`

Authorize media.ocr_pii.process.

Resource: `image`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `media.ocr_pii.read`

Authorize media.ocr_pii.read.

Resource: `image`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `media.pdf.view`

Authorize media.pdf.view.

Resource: `encounter_file`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=field_ophthalmologist,field_optometrist,optometrist,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)
- `signed_credential`: SessionChannelRequirement(channels=signed), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=target_active; expected=True), RelationshipRequirement(source=signed_credential; attributes=(); require_subject=False; require_scope=False)

### `mobile.context.view`

Authorize mobile.context.view.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `mobile.field.encounter.capture`

Authorize mobile.field.encounter.capture.

Resource: `encounter`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=field_ophthalmologist,field_optometrist,ophthalmologist,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `mobile.field.encounter.view`

Authorize mobile.field.encounter.view.

Resource: `encounter`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=field_ophthalmologist,field_optometrist,ophthalmologist,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `mobile.field.inference.run`

Authorize mobile.field.inference.run.

Resource: `encounter`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=field_ophthalmologist,field_optometrist,ophthalmologist,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `mobile.field.project.sync`

Authorize mobile.field.project.sync.

Resource: `project`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=field_ophthalmologist,field_optometrist,ophthalmologist,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `mobile.field.project.view`

Authorize mobile.field.project.view.

Resource: `project`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=field_ophthalmologist,field_optometrist,ophthalmologist,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `mobile.field.projects.list`

Authorize mobile.field.projects.list.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), AnyRoleRequirement(roles=field_ophthalmologist,field_optometrist,ophthalmologist,optometrist), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `mobile.session.detail.view`

Authorize mobile.session.detail.view.

Resource: `mobile_session`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `mobile.session.list`

Authorize mobile.session.list.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `mobile.session.revoke`

Authorize mobile.session.revoke.

Resource: `mobile_session`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `mobile.upload.create`

Authorize mobile.upload.create.

Resource: `project_upload_target`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_upload_profile`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), ScopedRoleRequirement(roles=field_ophthalmologist,field_optometrist,ophthalmologist,optometrist; allow_system=False), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), ScopedRoleRequirement(roles=admin; allow_system=True), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)

### `mobile.upload.inference.retry`

Authorize mobile.upload.inference.retry.

Resource: `job`; disclosure: `masked`; audit: `optional`.

- `mobile_owner`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=ownership; attributes=(); require_subject=True; require_scope=False), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=field_ophthalmologist,field_optometrist,ophthalmologist,optometrist; allow_system=False)
- `admin_owner`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=ownership; attributes=(); require_subject=True; require_scope=False), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `mobile.upload.options.view`

Authorize mobile.upload.options.view.

Resource: `user`; disclosure: `masked`; audit: `optional`.

- `self`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), BooleanRequirement(fact=self_identity; expected=True)

### `mobile.upload.view`

Authorize mobile.upload.view.

Resource: `job`; disclosure: `masked`; audit: `optional`.

- `mobile_owner`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=ownership; attributes=(); require_subject=True; require_scope=False), ScopedRoleRequirement(roles=field_ophthalmologist,field_optometrist,ophthalmologist,optometrist; allow_system=False)
- `admin_owner`: ActivePrincipalRequirement(authenticated=True), SessionChannelRequirement(channels=mobile), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=ownership; attributes=(); require_subject=True; require_scope=False), ScopedRoleRequirement(roles=admin; allow_system=True)

### `notifications.send`

Authorize notifications.send.

Resource: `notification_target`; disclosure: `masked`; audit: `optional`.

- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `preprocess.dashboard.view`

Authorize preprocess.dashboard.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=verifier), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `preprocess.image.update`

Authorize preprocess.image.update.

Resource: `image`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.access.manage`

Authorize project.access.manage.

Resource: `project`; disclosure: `masked`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=project_admin; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.encountersets.browse`

Authorize project.encountersets.browse.

Resource: `encounter_set`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=analytics_viewer,collaborator,data_exporter,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.encountersets.browse_pii`

Authorize project.encountersets.browse_pii.

Resource: `encounter_set`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=data_exporter,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.encountersets.workspace.view`

Authorize project.encountersets.workspace.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=analytics_viewer,collaborator,data_exporter,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `project.encountersets.workspace.view_pii`

Authorize project.encountersets.workspace.view_pii.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=data_exporter,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `project.grader_allocations.enforcement.manage`

Authorize project.grader_allocations.enforcement.manage.

Resource: `project`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=project_admin; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.grader_allocations.manage`

Authorize project.grader_allocations.manage.

Resource: `project_allocation_target`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_manager,project_admin; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.grader_allocations.view`

Authorize project.grader_allocations.view.

Resource: `project_allocation_plan`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=data_manager,project_admin,project_pi,site_pi; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.grants.view`

Authorize project.grants.view.

Resource: `project`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=local_admin,project_admin,project_pi,site_pi,user_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.site_policy.manage`

Authorize project.site_policy.manage.

Resource: `project_site_policy`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=project_admin; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.upload.create`

Authorize project.upload.create.

Resource: `project_upload_target`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_upload_profile`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=fileUploader,optometrist; allow_system=False), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=admin; allow_system=True), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)

### `project.upload.pregraded`

Authorize project.upload.pregraded.

Resource: `project_upload_target`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_upload_profile`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=pregraded_uploader; allow_system=False), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=admin; allow_system=True), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)

### `project.upload.workspace.view`

Authorize project.upload.workspace.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=analytics_viewer,collaborator,data_exporter,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `project.uploaders.manage`

Authorize project.uploaders.manage.

Resource: `project`; disclosure: `masked`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=project_admin,project_pi,site_pi; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.view`

Authorize project.view.

Resource: `project`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=analytics_viewer,collaborator,data_exporter,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.wai.results`

Authorize project.wai.results.

Resource: `project`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=analytics_viewer,collaborator,data_exporter,dataset_creator,discrepancy_reviewer,field_ophthalmologist,field_optometrist,ophthalmologist,optometrist,project_admin,project_pi,regrade_adjudicator,site_pi,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `project.wai.run`

Authorize project.wai.run.

Resource: `project`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=field_ophthalmologist,field_optometrist,optometrist,verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)
- `stored_automation_rule`: SessionChannelRequirement(channels=automation), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=automation_rule; attributes=(('target_matches', True),); require_subject=False; require_scope=True), BooleanRequirement(fact=domain_valid; expected=True)

### `public.analytics.view`

Authorize public.analytics.view.

Resource: `public`; disclosure: `masked`; audit: `optional`.

- `public`: PublicRequirement()

### `public.view`

Authorize public.view.

Resource: `public`; disclosure: `masked`; audit: `optional`.

- `public`: PublicRequirement()

### `reports.view`

Authorize reports.view.

Resource: `report`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `review.discrepancy.export`

Authorize review.discrepancy.export.

Resource: `discrepancy`; disclosure: `masked`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_exporter,data_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `review.discrepancy.export_identifiers`

Authorize review.discrepancy.export_identifiers.

Resource: `discrepancy`; disclosure: `identifier_release`; audit: `required`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_exporter,data_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `review.discrepancy.view`

Authorize review.discrepancy.view.

Resource: `discrepancy`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=discrepancy_reviewer; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `review.regrade.adjudicate`

Authorize review.regrade.adjudicate.

Resource: `grading_task`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=regrade_adjudicator; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `review.regrade_creator.manage`

Authorize review.regrade_creator.manage.

Resource: `grading_task`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `review.task.submit`

Authorize review.task.submit.

Resource: `grading_task`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=discrepancy_reviewer; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `review.task.view`

Authorize review.task.view.

Resource: `grading_task`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=discrepancy_reviewer; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `screenings.delete`

Authorize screenings.delete.

Resource: `encounter`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `screenings.reprocess`

Authorize screenings.reprocess.

Resource: `encounter`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=data_manager; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `screenings.view`

Authorize screenings.view.

Resource: `encounter`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `search.view`

Authorize search.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=data_manager,fileUploader,local_admin,ophthalmologist,optometrist), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `tasks.view`

Authorize tasks.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=collaborator,data_manager,fileUploader,local_admin,ophthalmologist,optometrist,project_admin,project_pi,site_pi), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `tasks.viewer.view`

Authorize tasks.viewer.view.

Resource: `image`; disclosure: `masked`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=collaborator,data_manager,fileUploader,local_admin,ophthalmologist,optometrist,project_admin,project_pi,site_pi; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `upload.create`

Authorize upload.create.

Resource: `upload_target`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_upload_profile`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=fileUploader,optometrist; allow_system=False), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=admin; allow_system=True), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)

### `upload.direct.batch.update`

Authorize upload.direct.batch.update.

Resource: `direct_upload_batch`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_manager,fileUploader,local_admin,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `upload.direct.edit_image`

Authorize upload.direct.edit_image.

Resource: `image`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=fileUploader,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `upload.direct.update`

Authorize upload.direct.update.

Resource: `direct_image_upload`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=data_manager,fileUploader,local_admin,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `upload.direct.view`

Authorize upload.direct.view.

Resource: `direct_image_upload`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=fileUploader,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `upload.pregraded.create`

Authorize upload.pregraded.create.

Resource: `upload_target`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_upload_profile`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=pregraded_uploader; allow_system=False), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), ScopedRoleRequirement(roles=admin; allow_system=True), BooleanRequirement(fact=exact_resource; expected=True), RelationshipRequirement(source=upload_profile; attributes=(('target_active', True),); require_subject=True; require_scope=True)

### `upload.pregraded.workspace.view`

Authorize upload.pregraded.workspace.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=pregraded_uploader), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `upload.workspace.view`

Authorize upload.workspace.view.

Resource: `screen`; disclosure: `masked`; audit: `optional`.

- `authenticated_screen`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=data_manager,fileUploader,local_admin,ophthalmologist,optometrist), GrantSourceRequirement(sources=authorization_grant)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), AnyRoleRequirement(roles=admin), GrantSourceRequirement(sources=authorization_grant)

### `upload.zip.view`

Authorize upload.zip.view.

Resource: `upload_job`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=fileUploader,optometrist; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `verification.direct.update`

Authorize verification.direct.update.

Resource: `direct_image_upload`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `verification.direct.view`

Authorize verification.direct.view.

Resource: `direct_image_upload`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `verification.encounter_set.update`

Authorize verification.encounter_set.update.

Resource: `encounter`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `verification.encounter_set.view`

Authorize verification.encounter_set.view.

Resource: `encounter`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

### `verification.remidio.update`

Authorize verification.remidio.update.

Resource: `encounter`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), BooleanRequirement(fact=domain_valid; expected=True), ScopedRoleRequirement(roles=admin; allow_system=True)

### `verification.remidio.view`

Authorize verification.remidio.view.

Resource: `encounter`; disclosure: `identifier_in_place`; audit: `optional`.

- `scoped_role`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=verifier; allow_system=False)
- `admin_break_glass`: ActivePrincipalRequirement(authenticated=True), BooleanRequirement(fact=exact_resource; expected=True), IdentifierReleaseRequirement(), ScopedRoleRequirement(roles=admin; allow_system=True)

## Roles

- `admin` — System administration and break-glass. Scopes: `system`.
- `analytics_viewer` — Scoped masked analytics. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
- `collaborator` — Scoped masked project collaboration. Scopes: `project`, `project_lab_unit`.
- `data_exporter` — Dataset and review export. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
- `data_manager` — Scoped data operations. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
- `dataset_creator` — Dataset assembly and curation. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
- `discrepancy_reviewer` — Scoped discrepancy review. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
- `field_ophthalmologist` — Project field capture as ophthalmologist. Scopes: `project`, `project_lab_unit`.
- `field_optometrist` — Project field capture as optometrist. Scopes: `project`, `project_lab_unit`.
- `fileUploader` — Scoped upload operations. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
- `local_admin` — Hospital operations without user-delegation authority. Scopes: `hospital`.
- `ophthalmologist` — Clinical grading qualification. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
- `optometrist` — Clinical capture and upload operations. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
- `pii_exporter` — Additive authority to release identifiers. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
- `pregraded_uploader` — Scoped pregraded uploads. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
- `project_admin` — Project or project-site access administration. Scopes: `project`, `project_lab_unit`.
- `project_pi` — Project-wide scientific oversight. Scopes: `project`.
- `regrade_adjudicator` — Scoped regrade adjudication. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
- `site_pi` — Project-site scientific oversight. Scopes: `project_lab_unit`.
- `user_manager` — User administration within a hospital. Scopes: `hospital`.
- `verifier` — Encounter and image verification. Scopes: `hospital`, `lab_unit`, `project`, `project_lab_unit`.
