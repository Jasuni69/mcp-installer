# CI/CD Workflow Guide

## Connecting a Workspace to Git

1. `set_workspace("My Dev Workspace")`
2. `git_connect(git_provider_type="AzureDevOps", organization_name="MyOrg", project_name="MyProject", repository_name="fabric-repo", branch_name="main", directory_name="dev")`
3. `git_initialize_connection(initialization_strategy="PreferWorkspace")` — first sync
4. `git_get_status()` — check what changed

## Committing Changes

1. `git_get_status()` — get workspaceHead and see changes
2. `git_commit_to_git(workspace_head="<sha>", comment="Added new measures")`

## Pulling from Git

1. `git_get_status()` — get remoteCommitHash
2. `git_update_from_git(remote_commit_hash="<sha>", conflict_resolution_policy="PreferRemote", allow_override_items=True)`

## Deploying Across Environments

1. `list_deployment_pipelines()` — find pipeline ID
2. `list_deployment_pipeline_stages(pipeline_id)` — get stage IDs
3. `deploy_stage_content(pipeline_id, source_stage_id="<dev>", target_stage_id="<test>", note="Sprint 42 release")`
