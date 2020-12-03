from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import JsonResponse, HttpResponse
from django.template.loader import get_template
from django.conf import settings
from django.core.files.base import ContentFile
from django.utils.text import slugify

import os
import shutil
import subprocess
from tempfile import mkdtemp
from urllib import parse

from ..utils.stats import generic_stats


TEMP_PREFIX = getattr(settings, 'PDF_TEMP_PREFIX', 'render_pdf-')
CACHE_PREFIX = getattr(settings, 'PDF_CACHE_PREFIX', 'render-pdf')
CACHE_TIMEOUT = getattr(settings, 'PDF_CACHE_TIMEOUT', 30), # 86400)  # 1 day


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Mixin to allow access through a view only if the user is a superuser.
    Can be used with any View.
    """
    def test_func(self):
        return self.request.user.is_superuser


class AsyncFormMixin(object):
    """
    Mixin to add AJAX support to a form.
    Must be used with an object-based FormView (e.g. CreateView)
    """
    modal_response = False

    def form_valid(self, form):
        # We make sure to call the parent's form_valid() method because
        # it might do some processing (in the case of CreateView, it will
        # call form.save() for example).
        response = super().form_valid(form)
        if self.request.is_ajax():
            data = {
                'modal': self.modal_response,
                'url': self.get_success_url(),
            }
            return JsonResponse(data, safe=False)
        else:
            return response


class HTML2PdfMixin(object):
    """
    Mixin to create a .pdf file from a HTML template.
    """

    def get_template_name(self):
        return "lims/base.html"

    def get(self, request, *args, **kwargs):
        object = self.get_object()
        name = slugify(object.name)
        context = self.get_template_context()
        context['request'] = request
        template = get_template(self.get_template_name())

        rendered_tpl = template.render(context).encode('utf-8')

        tmp = mkdtemp(prefix=TEMP_PREFIX)
        html_file = os.path.join(tmp, '{}.html'.format(name))
        f = open(html_file, 'w')
        f.write(rendered_tpl.decode())
        f.close()
        pdf_filename = "{}/{}.pdf".format(tmp, name)
        try:
            cmd = 'xvfb-run wkhtmltopdf -L 25mm -R 25mm -T 20mm -B 20mm -s Letter {0}.html {0}.pdf'.format(name)
            subprocess.call(cmd.split(), cwd=tmp)
            pdf = open(pdf_filename, 'rb').read()

        finally:
            shutil.rmtree(tmp)

        pdf_file = ContentFile(pdf)
        res = HttpResponse(pdf_file, "application/pdf")
        res['Content-Length'] = pdf_file.size
        res['Content-Disposition'] = 'attachment; filename="{}"'.format(os.path.basename(pdf_filename))
        return res


class PlotViewMixin():
    template_name = "lims/list-plots.html"
    plot_fields = []
    date_field = None
    paginate_by = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['report'] = self.get_metrics()
        context['active_filters'] = self.get_active_filters()
        return context

    def get_plot_fields(self):
        return self.plot_fields

    def get_active_filters(self):
        qsl = self.get_query_string()
        if self.date_field:
            for part in ['year', 'month', 'day', 'quarter']:
                qsl = qsl.replace('{}_{}'.format(self.date_field, part), '{}__{}'.format(self.date_field, part))
        return dict(parse.parse_qsl(qsl.strip('?')))

    def get_metrics(self):
        return generic_stats(self.get_queryset(), self.get_plot_fields(), self.date_field)
