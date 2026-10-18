from __future__ import annotations
import uuid
from pathlib import Path
import numpy as np
from PIL import Image
from backend.registry import all_modules, GROUPS
from backend.core.image_context import ImageContext
from backend.core.engine import run_modules

def make_test_image(path):
    y, x = np.mgrid[0:180, 0:260]
    arr = np.stack(((x * 3 + y) % 256, (y * 5) % 256, (((x // 9 + y // 9) % 2) * 210 + 20)), axis=2).astype(np.uint8)
    Image.fromarray(arr, 'RGB').save(path)
    return path

def test_registry_has_unique_module_ids():
    modules = all_modules()
    ids = [m['id'] for m in modules]
    assert len(modules) == 44
    assert len(ids) == len(set(ids))
    assert len(GROUPS) == 8

def test_all_modules_return_results_without_uncaught_errors(tmp_path):
    path = make_test_image(tmp_path / 'fixture.png')
    sid = str(uuid.uuid4())
    ctx = ImageContext(path=path, session_id=sid, result_dir=tmp_path / 'artifacts', source_filename='fixture.png')
    results = run_modules(ctx, [m['id'] for m in all_modules()])
    assert len(results) == 44
    assert all(r.get('module_id') and r.get('name') and 'status' in r for r in results)
    assert not [r for r in results if r['status'] == 'error']
    assert any(r['module_id'] == 'autostereogram' and r['visuals'] for r in results)
    assert any(r['module_id'] == 'payload_analysis' for r in results)
    assert len(list((tmp_path / 'artifacts').glob('*.png'))) >= 45

def test_image_info_preserves_original_digest_and_file_size(tmp_path):
    path = make_test_image(tmp_path / 'fixture.png')
    sid = str(uuid.uuid4())
    ctx = ImageContext(path=path, session_id=sid, result_dir=tmp_path / 'artifacts', source_filename='chosen-name.png')
    result = run_modules(ctx, ['image_info'])[0]
    assert result['metrics']['filename'] == 'chosen-name.png'
    assert len(result['metrics']['sha256']) == 64
    assert result['metrics']['file_size_human']

def test_image_outputs_are_separate_and_text_preview_is_readable(tmp_path):
    path = make_test_image(tmp_path / 'visual-fixture.png')
    sid = str(uuid.uuid4())
    artifact_dir = tmp_path / 'visual-artifacts'
    ctx = ImageContext(path=path, session_id=sid, result_dir=artifact_dir, source_filename='visual-fixture.png')
    ids = ['channels', 'bit_extraction', 'bit_planes', 'bitstream', 'channel_order', 'visualization']
    results = run_modules(ctx, ids)
    by_id = {result['module_id']: result for result in results}

    assert all(by_id[module_id]['status'] != 'error' for module_id in ids)
    assert len(by_id['channels']['visuals']) == 4
    assert len(by_id['bit_extraction']['visuals']) == 6
    assert len(by_id['bit_planes']['visuals']) == 8
    assert len(by_id['channel_order']['visuals']) == 3
    assert len(by_id['visualization']['visuals']) == 4

    bitstream_path = artifact_dir / Path(by_id['bitstream']['visuals'][0]['url']).name
    with Image.open(bitstream_path) as visual:
        assert visual.size == (1680, 760)

    bit_plane_path = artifact_dir / Path(by_id['bit_extraction']['visuals'][0]['url']).name
    with Image.open(bit_plane_path) as visual:
        assert visual.size == (260, 180)


def test_native_chart_payloads_use_measured_image_data(tmp_path):
    path = make_test_image(tmp_path / 'chart-fixture.png')
    sid = str(uuid.uuid4())
    ctx = ImageContext(path=path, session_id=sid, result_dir=tmp_path / 'chart-artifacts', source_filename='chart-fixture.png')
    results = run_modules(ctx, ['histogram', 'color_distribution', 'correlation', 'dct_analysis'])
    by_id = {result['module_id']: result for result in results}

    histogram = by_id['histogram']
    assert histogram['chart']['type'] == 'line'
    assert len(histogram['chart']['series']) == 4
    pixel_count = 260 * 180
    assert all(len(series['values']) == 64 for series in histogram['chart']['series'])
    assert all(sum(series['values']) == pixel_count for series in histogram['chart']['series'])
    assert histogram['visuals'] == []  # Histogram is rendered as a browser-native SVG, not a PNG chart.

    colors = by_id['color_distribution']
    assert colors['chart']['type'] == 'bar'
    assert 1 <= len(colors['chart']['items']) <= 8
    assert all(0 <= item['value'] <= 100 and item['color'].startswith('#') for item in colors['chart']['items'])
    assert colors['visuals'] == []  # Dominant colours are real chart bars with hover values.

    assert by_id['correlation']['chart']['type'] == 'line'
    assert len(by_id['correlation']['chart']['series'][0]['values']) <= 100
    assert by_id['dct_analysis']['chart']['type'] == 'line'
    assert all(visual['label'] != 'DCT AC histogram' for visual in by_id['dct_analysis']['visuals'])
