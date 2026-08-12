# -*- coding: utf-8 -*-
from unittest.mock import patch

import resources.lib.web as web_module


def test_channel_disable_always_saves(monkeypatch):
    saved = []

    def fake_save(disabled_channels):
        saved.append(list(disabled_channels))

    monkeypatch.setattr(web_module, 'load_diasbled_channels', lambda: [])
    monkeypatch.setattr(web_module, 'save_disabled_channels', fake_save)

    web_module.channel('ch1', 'disable')
    web_module.channel('ch1', 'disable')

    assert len(saved) == 2
    assert saved[0] == ['ch1']
    assert saved[1] == ['ch1']


def test_channel_enable_always_saves(monkeypatch):
    saved = []

    def fake_save(disabled_channels):
        saved.append(list(disabled_channels))

    monkeypatch.setattr(web_module, 'load_diasbled_channels', lambda: ['ch1'])
    monkeypatch.setattr(web_module, 'save_disabled_channels', fake_save)

    web_module.channel('ch1', 'enable')

    assert len(saved) == 1
    assert saved[0] == []
