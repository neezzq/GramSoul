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
