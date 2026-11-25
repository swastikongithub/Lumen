from app.ingest.html_clean import clean_html

PAGE = """
<html><head><style>.x{}</style><script>track()</script></head>
<body>
  <header><nav><a href="/">Home</a> <a href="/admissions">Admissions</a></nav></header>
  <div id="wrapper">
    <ol class="breadcrumb"><li>Home</li><li>SDG 10</li></ol>
    <h2>Anti Ragging Policy</h2>
    <p>Ragging is totally prohibited in the University.</p>
    <table><tr><td>Helpline</td><td>1800-180-5522</td></tr></table>
    <form id="callform"><h2>Talk to an Admissions Advisor</h2><input name="phone"></form>
  </div>
  <div id="live-video-counselling" class="modal fade"><h2>Register for Video Counselling</h2></div>
  <div role="dialog"><p>Reserved seats 2026-2027</p></div>
  <footer><p>Copyright LPU</p></footer>
</body></html>
"""


def test_keeps_the_policy_text_and_tables() -> None:
    cleaned = clean_html(PAGE)

    assert "Anti Ragging Policy" in cleaned
    assert "Ragging is totally prohibited" in cleaned
    assert "<table>" in cleaned and "1800-180-5522" in cleaned


def test_removes_menus_modals_forms_and_footer() -> None:
    cleaned = clean_html(PAGE)

    for chrome in (
        "Admissions",
        "SDG 10",
        "Talk to an Admissions Advisor",
        "Video Counselling",
        "Reserved seats",
        "Copyright",
        "track()",
    ):
        assert chrome not in cleaned
