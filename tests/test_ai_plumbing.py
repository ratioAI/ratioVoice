"""Prüft die Datenwege des RVC-Backends mit winzigen Platzhalter-Modellen.

Die Platzhalter haben dieselben Ein- und Ausgänge wie echte ContentVec- bzw.
RVC-v2-Exporte, aber keine sinnvollen Gewichte. Getestet wird also nur, dass
Formen, Typen, Zerlegung in Abschnitte und Abtastraten zusammenpassen – nicht
die Klangqualität echter Modelle.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

onnx = pytest.importorskip("onnx")
pytest.importorskip("onnxruntime")
from onnx import TensorProto, helper, numpy_helper  # noqa: E402


def _save(path, nodes, inputs, outputs, initializers):
    graph = helper.make_graph(nodes, "g", inputs, outputs, initializers)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))


def _fake_encoder(path):
    weight = numpy_helper.from_array(np.full((768, 1, 320), 1e-3, dtype=np.float32), "w")
    nodes = [
        helper.make_node("Conv", ["source", "w"], ["c"], strides=[320]),
        helper.make_node("Transpose", ["c"], ["feats"], perm=[0, 2, 1]),
    ]
    _save(path, nodes,
          [helper.make_tensor_value_info("source", TensorProto.FLOAT, [1, 1, None])],
          [helper.make_tensor_value_info("feats", TensorProto.FLOAT, [1, None, 768])], [weight])


def _fake_voice(path, samples_per_frame=400):
    weight = numpy_helper.from_array(np.full((1, 1, samples_per_frame), 1e-3, dtype=np.float32), "w")
    axes = numpy_helper.from_array(np.array([1], dtype=np.int64), "axes")
    nodes = [
        helper.make_node("Unsqueeze", ["pitchf", "axes"], ["p"]),
        helper.make_node("ConvTranspose", ["p", "w"], ["audio"], strides=[samples_per_frame]),
    ]
    info = helper.make_tensor_value_info
    inputs = [
        info("phone", TensorProto.FLOAT, [1, None, 768]),
        info("phone_lengths", TensorProto.INT64, [1]),
        info("pitch", TensorProto.INT64, [1, None]),
        info("pitchf", TensorProto.FLOAT, [1, None]),
        info("ds", TensorProto.INT64, [1]),
        info("rnd", TensorProto.FLOAT, [1, 192, None]),
    ]
    _save(path, nodes, inputs, [info("audio", TensorProto.FLOAT, [1, 1, None])], [weight, axes])


def test_rvc_pipeline_shapes(tmp_path, monkeypatch):
    from ratiovoice import audio_io, config
    from ratiovoice.ai import rvc

    monkeypatch.setattr(config, "models_dir", lambda: tmp_path)
    monkeypatch.setattr(rvc, "models_dir", lambda: tmp_path)
    _fake_encoder(tmp_path / rvc.ENCODER_NAMES[0])
    _fake_voice(tmp_path / "Teststimme.onnx")

    assert rvc.list_models() == ["Teststimme"]
    speech = audio_io.load(Path(__file__).parent / "data" / "sprache_1.wav")
    long_take = np.tile(speech, 6)  # ~20 s -> erzwingt zwei Abschnitte mit Überblendung
    converter = rvc.RvcConverter("Teststimme")
    assert converter.uses_pitch
    out = converter.convert(long_take, transpose=3)
    assert out.shape == long_take.shape and out.dtype == np.float32
    assert np.isfinite(out).all() and np.abs(out).max() > 0
