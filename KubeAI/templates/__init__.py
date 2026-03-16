"""Template mounts are the Helm-chart analogue for composing agent capabilities at spawn time."""

from .base import (
	Template,
	TemplateConfig,
	TemplateError,
	TemplateHookError,
	TemplateMountError,
	attach_template,
	attach_templates,
	detach_templates,
	get_attached_templates,
	run_post_hooks,
	run_pre_hooks,
)

__all__ = [
	"Template",
	"TemplateConfig",
	"TemplateError",
	"TemplateHookError",
	"TemplateMountError",
	"attach_template",
	"attach_templates",
	"detach_templates",
	"get_attached_templates",
	"run_post_hooks",
	"run_pre_hooks",
]
