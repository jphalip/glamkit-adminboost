from django import forms
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import ugettext as _
from django.utils.safestring import mark_safe
from django.contrib.admin.options import InlineModelAdmin
from django.conf import settings
from django.utils.encoding import force_unicode


from adminboost.utils import import_from_string


# Engines --------------------------------------------------------------------


class ThumbnailEngine():

    def get_image_template(self):
        raise NotImplementedError

    def get_thumbnail_url(self, image, options):
        raise NotImplementedError


class DummyEngine(ThumbnailEngine):

    def get_thumbnail_url(self, image, options):
        raise ImproperlyConfigured(
            'You need to install either easy_thumbnails or sorl-thumbnail for '
            'the adminboost preview functionality to work.')


class EasyThumbnailEngine(ThumbnailEngine):

    def get_image_template(self):
        return 'adminboost/_easythumbnails_preview_image.html'

    def get_thumbnail_url(self, image, options):
        from easy_thumbnails.files import get_thumbnailer
        thumbnail = get_thumbnailer(image).get_thumbnail(options)
        return thumbnail.url


class SorlThumbnailEngine(ThumbnailEngine):

    def get_image_template(self):
        return 'adminboost/_sorlthumbnail_preview_image.html'

    def get_thumbnail_url(self, image, options):
        from sorl.thumbnail import get_thumbnail
        thumbnail = get_thumbnail(image.file, '%sx%s' % options['size'], crop=options['crop'])
        return thumbnail.url


_preview_engine_cache = None

def get_preview_engine():
    global _preview_engine_cache
    if _preview_engine_cache is None:
        if hasattr(settings, 'ADMINBOOST_PREVIEW_ENGINE'):
            _preview_engine_cache = import_from_string(settings.ADMINBOOST_PREVIEW_ENGINE)()
        else:
            try:
                import easy_thumbnails
                easy_thumbnails_available = True
            except ImportError:
                easy_thumbnails_available = False

            try:
                from sorl import thumbnail
                sorl_thumbnail_available = True
            except ImportError:
                sorl_thumbnail_available = False

            if easy_thumbnails_available:
                # Default for legacy reasons (easy_thumbnails used to be the only available engine)
                _preview_engine_cache = EasyThumbnailEngine()
            elif sorl_thumbnail_available:
                _preview_engine_cache = SorlThumbnailEngine()
            else:
                _preview_engine_cache = DummyEngine()
    return _preview_engine_cache


# Admin classes ------------------------------------------------------------


class PreviewInline(InlineModelAdmin):
    """
    The 'preview' "field" should be present in the ModelForm used
    (see ModelForm classes below), but won't be actually rendered unless
    picked up via django.contrib.admin.helpers.InlineAdminFormSet.fields.

    Injecting it via get_fieldsets is a relatively straightforward way of
    enabling this, and bypasses Django's validation system for checking
    field names that actually exist.
    """

    def get_fieldsets(self, request, obj=None):
        """ Identical to standard code apart from inserting ['preview'] """
        if self.declared_fieldsets:
            return self.declared_fieldsets
        form = self.get_formset(request, obj).form
        fields = ['preview'] + list(form.base_fields) + list(
            self.get_readonly_fields(request, obj)
        )
        return [(None, {'fields': fields})]


class PreviewStackedInline(PreviewInline):
    template = 'admin/edit_inline/stacked.html'


class PreviewTabularInline(PreviewInline):
    template = 'admin/edit_inline/tabular.html'


# Form classes ------------------------------------------------------------


class PreviewWidget(forms.widgets.Input):
    is_hidden = False
    input_type = 'text'

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        self.form = kwargs.pop('form', None)
        super(PreviewWidget, self).__init__(*args, **kwargs)


class ImagePreviewWidget(PreviewWidget):

    def render(self, name, data, attrs=None):

        if not self.form.preview_instance_required or self.instance is not None:
            images = self.form.get_images(self.instance)
            options = dict(size=(120, 120), crop=False)
            html = u'<div class="adminboost-preview">'
            for image in images:
                thumbnail_url = get_preview_engine().get_thumbnail_url(image, options)
                html += (
                    u'<div class="adminboost-preview-thumbnail">'
                    u'<a href="%(image_url)s" target="_blank">'
                    u'<img src="%(thumbnail_url)s"/></a></div>' % {
                        'image_url': image.url,
                        'thumbnail_url': thumbnail_url
                    }
                )
            help_text = self.form.get_preview_help_text(self.instance)
            if help_text is not None:
                html += u'<p class="help">%s</p>' % force_unicode(help_text)
            html += u'</div>'
            return mark_safe(unicode(html))
        else:
            return u''


class PreviewField(forms.Field):
    """ Dummy "field" to provide preview thumbnail. """
    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        self.form = kwargs.pop('form', None)
        kwargs['widget'] = self.form.preview_widget_class(
            instance=self.instance, form=self.form)
        super(PreviewField, self).__init__(*args, **kwargs)


class PreviewInlineForm(forms.ModelForm):
    # If True, the widget will only be displayed if an
    # instance of the model exists (i.e. the object
    # has already been saved at least once).
    preview_instance_required = True

    def __init__(self, *args, **kwargs):
        super(PreviewInlineForm, self).__init__(*args, **kwargs)
        preview_field = PreviewField(
            label = _('Preview'), required=False,
            instance = kwargs.get('instance', None), form=self)
        self.fields.insert(0, 'preview', preview_field)
        self.base_fields.insert(0, 'preview', preview_field)

    class Media:
        css = {
            'all': ("%sadminboost/styles.css" % settings.STATIC_URL,)
        }


class ImagePreviewInlineForm(PreviewInlineForm):

    preview_widget_class = ImagePreviewWidget

    def get_preview_help_text(self, instance):
        """
        Returns text that should be displayed under
        the image(s). Useful for example to display a
        disclaimer about the preview
        """

    def get_images(self, instance): # TODO: Rename to get_preview_images
        """
        This needs to be specified by the child
        form class, as we cannot anticipate the name of the image model field
        """
        raise NotImplementedError()
