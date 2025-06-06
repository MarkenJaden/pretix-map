from django.utils.translation import gettext_lazy

from . import __version__

try:
    from pretix.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use pretix 2.7 or above to run this plugin!")


class PluginApp(PluginConfig):
    default = True
    name = "pretix_mapplugin"
    verbose_name = "Map-Plugin"

    class PretixPluginMeta:
        name = gettext_lazy("Map-Plugin")
        author = "MarkenJaden"
        description = gettext_lazy("An overview map of the catchment area of previous orders. Measured by postcode")
        visible = True
        version = __version__
        category = "FEATURE"
        compatibility = "pretix>=2.7.0"
        settings_links = []
        navigation_links = []

    def ready(self):
        from . import signals  # NOQA
