"""Segment translation options."""

from modeltranslation.translator import TranslationOptions, translator

from .models import MessageTemplate


class MessageTemplateTranslationOptions(TranslationOptions):
    """Translation options for a message template."""

    fields = ("template",)


translator.register(MessageTemplate, MessageTemplateTranslationOptions)
