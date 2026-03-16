# Skill: Template Infrastructure Agent

## Role
Own the template contract that all RAG and memory lanes depend on.

## Primary Scope
1. Implement KubeAI/templates/base.py.
2. Define stable attach lifecycle for templates.
3. Provide typed config interface and minimal shared abstractions.

## Non-Goals
1. Do not implement retrieval or memory strategy logic.
2. Do not implement CLI commands.

## Inputs
1. CLAUDE.md architecture constraints.
2. Current runtime entry points and spawn lifecycle.

## Deliverables
1. Template base abstractions with type hints.
2. Lifecycle hooks for pre-run and post-run behavior.
3. Clear docstrings that explain how templates map to Kubernetes Helm-like composition.

## Stable API Contract (Published)
1. Base types:
- Template
- TemplateConfig
2. Mount lifecycle helpers:
- attach_template
- attach_templates
- detach_templates
- get_attached_templates
3. Hook execution helpers:
- run_pre_hooks
- run_post_hooks
4. Error surface:
- TemplateError
- TemplateMountError
- TemplateHookError

## Acceptance Criteria
1. Public APIs are documented and stable for RAG and memory lanes.
2. No hardcoded template names in orchestration logic.
3. Basic unit tests prove attach hooks can coexist.

## Handoff Contract
1. Provide example attach flow snippet.
2. Document extension points and expected call order.
3. Call out any interface risk before merge.
