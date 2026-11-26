from app import prompt as P


def card(name, role="npc", **kw):
    return P.Card(id=hash(name), public_id="p_" + name, role=role, name=name, **kw)


def test_parse_speakers_and_actions():
    raw = "Рассказчик: Ветер стих.\nИва: *сжимает пальцы* Я тут.\nЯн: *встаю* Пойдём!\nХаритон: Эх, юнга!"
    out = P.parse_output(raw, ["Ива", "Харитон"], ["Ян", "Лада"])
    assert [(p.kind, p.name) for p in out] == [("narrator", "Рассказчик"), ("character", "Ива"), ("character", "Харитон")]
    assert all("встаю" not in p.text for p in out)  # never speaks for a player's hero


def test_parse_drops_repeats_and_empty_actions():
    hist = ["Полночь. Винтовая лестница наконец кончается, и вы выходите на верхнюю галерею маяка."]
    raw = "Рассказчик: Полночь. Винтовая лестница наконец кончается, и вы выходите на верхнюю галерею маяка.\nХаритон: **\nИва: *вздрагивает* Слышишь?"
    out = P.parse_output(raw, ["Ива", "Харитон"], ["Ян"], history=hist)
    assert [(p.name, p.text) for p in out] == [("Ива", "*вздрагивает* Слышишь?")]


def test_unlabelled_text_is_narration_and_unpaired_star_closed():
    out = P.parse_output("Где-то хлопнула дверь.\nИва: *прячется за Яна", ["Ива"], ["Ян"])
    assert out[0].kind == "narrator" and out[1].text.endswith("*")


def test_prompt_fits_context_and_contains_cards():
    iva = card("Ива", personality="Дерзкая и насмешливая", habits="x" * 3000, backstory="y" * 3000)
    hero = card("Ян", role="hero", personality="спокойный")
    hist = [P.HistoryItem(i, "player" if i % 2 else "character", "Ян" if i % 2 else "Ива", "слово " * 120) for i in range(30)]
    inp = P.PromptInput(title="Т", description="d", world_rules="w" * 3000, location="маяк", npcs=[iva],
                        seats=[P.Seat("mira", "Ян", hero)], summary="s" * 2000, history=hist,
                        facts=["Ян — берёт за руку"], mode="reply", num_ctx=2048, num_predict=220)
    b = P.build(inp)
    total = sum(len(m["content"]) for m in b.messages)
    assert total <= (2048 - 220 - 120) * P.CHARS_PER_TOKEN
    assert "Дерзкая и насмешливая" in b.messages[0]["content"]
    assert b.messages[-1]["role"] == "user" and "Не пиши за героев игроков (Ян)" in b.messages[-1]["content"]
    assert "\nЯн:" in b.stop


def test_nested_label_hero_is_dropped():
    out = P.parse_output("Рассказчик: Лада: *щёлкаю зажигалкой* Ива, спой?\nИва: *улыбается* Ладно.", ["Ива"], ["Ян", "Лада"])
    assert [(p.name, p.text) for p in out] == [("Ива", "*улыбается* Ладно.")]


def test_echoed_scene_state_is_removed():
    raw = ("Рассказчик: *туман ползёт* Теперь всё в порядке.\nВерхняя галерея маяка. Рядом: Ян, Ива. Уже произошло: Ива — плачет]\n"
           "[Место: маяк. Рядом: Ян]\nИва: Пойдём.")
    out = P.parse_output(raw, ["Ива"], ["Ян"])
    texts = " ".join(p.text for p in out)
    assert "Рядом:" not in texts and "Уже произошло" not in texts and "Место:" not in texts
    assert out[-1].name == "Ива" and out[-1].text == "Пойдём."


def test_copied_location_line_dropped():
    hist = ["[Место: Верхняя галерея старого маяка, полночь. Линза погасла, внизу светится песок. Рядом: Ян]"]
    raw = "Рассказчик: Ветер стихает.\nВерхняя галерея старого маяка, полночь. Линза погасла"
    out = P.parse_output(raw, ["Ива"], ["Ян"], history=hist)
    assert [p.text for p in out] == ["Ветер стихает."]


def test_echo_of_scene_facts_is_dropped():
    facts = ["Ива — не сводит глаз с тумана", "Харитон — кричит снизу и стучит посохом по камню"]
    raw = ("Рассказчик: Ива - не сводит глаз с тумана; Харитон - кричит снизу и стучит посохом по камню.\n"
           "Ива: *вздрагивает* Ты слышал? Колокол!")
    out = P.parse_output(raw, ["Ива", "Харитон"], ["Ян"], facts=facts)
    assert [(p.name, p.text) for p in out] == [("Ива", "*вздрагивает* Ты слышал? Колокол!")]
    # a real narration that merely mentions the same people stays
    raw2 = "Рассказчик: Ива не сводит глаз с тумана, а внизу вдруг гаснет фонарь Харитона, и становится тихо."
    assert len(P.parse_output(raw2, ["Ива", "Харитон"], ["Ян"], facts=facts)) == 1


def test_short_player_lines_do_not_make_everything_a_repeat():
    raw = ("Рассказчик: Ночной город за окном мерцает россыпью огней, где-то на кухне капает кран.\n\n"
           "ММ: *откидывается на спинку* А — это первая буква и первое слово. Ты устал, я вижу.")
    for short in ("А", "да", "ок", "Ну?"):
        out = P.parse_output(raw, ["ММ"], ["Ян"], history=["ночь огни и все так и не спит", short], facts=[])
        assert [p.name for p in out] == ["Рассказчик", "ММ"], short
    # a real copy of an earlier long line is still dropped
    old = "Ночной город за окном мерцает россыпью огней, где-то на кухне капает кран."
    out = P.parse_output(raw, ["ММ"], ["Ян"], history=[old])
    assert [p.name for p in out] == ["ММ"]


def test_photo_prompt_follows_the_player_and_keeps_adults():
    hist = [P.HistoryItem(1, "character", "Адриан", "*прижимает блондина к двери* — Имя. Быстро.")]
    p = P.image_prompt("Хеллоу", "Магическая академия", "Коридор у спален", [], hist, "поле, усыпанное цветами")
    assert p.startswith("Нарисуй одну иллюстрацию: поле, усыпанное цветами.")
    assert "Коридор у спален" not in p  # the scene place must not override the request
    assert "взрослые (18+)" in p
    plain = P.image_prompt("Хеллоу", "", "Коридор у спален", [], hist, "")
    assert "Место: Коридор у спален." in plain and "взрослые (18+)" in plain


def test_style_asks_for_dashes():
    inp = P.PromptInput(title="T", description="", world_rules="", location="", npcs=[], seats=[], summary="",
                        history=[], facts=[], mode="reply", num_ctx=2048, num_predict=200)
    sys_text = P.build(inp).messages[0]["content"]
    assert "реплики — с тире" in sys_text and "— Слышишь?" in sys_text
