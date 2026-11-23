from coppersushi.frontend.packaging.shell import render_shell

def test_standalone_opf_routes_need_no_dash(monkeypatch):
    from coppersushi.frontend.packaging.preview import server
    monkeypatch.setenv('MAPBOX_TOKEN', 'test-token')
    for path, embed in [('/opf-2024', False), ('/embed/opf-2024', True)]:
        page = server.test_client().get(path).get_data(as_text=True)
        assert page == render_shell('test-token', embed=embed, view='opf')
        assert '/assets/opf-app.js' in page
        assert '_dash' not in page
