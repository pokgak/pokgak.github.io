"""Animated overview of the span lifecycle described in the Slack OTel article."""

import manimgx as m


m.config.pixel_width = 1280
m.config.pixel_height = 720
m.config.frame_rate = 30
m.config.background_color = "#0B1020"

BG = "#0B1020"
PANEL = "#151D33"
PANEL_ALT = "#1D2843"
TEXT = "#F8FAFC"
MUTED = "#B7C2D8"
LINE = "#64748B"
CYAN = "#67E8F9"
GREEN = "#86EFAC"
YELLOW = "#FDE68A"
PURPLE = "#D8B4FE"
CORAL = "#FDA4AF"


def body_text(content: str, size: int, color: str = TEXT) -> m.Text:
    return m.Text(
        content,
        font="sans-serif",
        font_size=size,
        weight=m.NORMAL,
        color=color,
    )


def label_text(content: str, size: int, color: str = TEXT) -> m.Text:
    return m.Text(
        content,
        font="sans-serif",
        font_size=size,
        weight=m.MEDIUM,
        color=color,
    )


def heading_text(content: str, size: int, color: str = TEXT) -> m.Text:
    return m.Text(
        content,
        font="sans-serif",
        font_size=size,
        weight=m.SEMIBOLD,
        color=color,
    )


def result_text(content: str, size: int, color: str = TEXT) -> m.Text:
    return m.Text(
        content,
        font="sans-serif",
        font_size=size,
        weight=m.BOLD,
        color=color,
    )


def code_text(content: str, size: int, color: str = TEXT) -> m.Text:
    return m.Text(
        content,
        font="monospace",
        font_size=size,
        weight=m.NORMAL,
        color=color,
    )


def code_label_text(content: str, size: int, color: str = TEXT) -> m.Text:
    return m.Text(
        content,
        font="monospace",
        font_size=size,
        weight=m.MEDIUM,
        color=color,
    )


def inline_text(
    parts: list[tuple[str, bool]], size: int, color: str = TEXT
) -> m.VGroup:
    fragments = [
        code_text(content, size, color) if is_code else body_text(content, size, color)
        for content, is_code in parts
    ]
    return m.VGroup(*fragments).arrange(m.RIGHT, buff=0.08)


def box(width: float, height: float, color: str = LINE) -> m.RoundedRectangle:
    return m.RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.16,
        color=color,
        fill_color=PANEL,
        fill_opacity=1,
        stroke_width=2,
    )


def labelled_box(
    heading: str,
    detail: str,
    width: float,
    color: str,
    detail_is_code: bool = False,
) -> m.VGroup:
    outline = box(width, 1.15, color)
    heading_label = label_text(heading, 21, color)
    detail_label = (
        code_text(detail, 24) if detail_is_code else body_text(detail, 24)
    )
    labels = m.VGroup(heading_label, detail_label).arrange(m.DOWN, buff=0.11)
    labels.move_to(outline)
    return m.VGroup(outline, labels)


def action_chip(label: str, color: str) -> m.VGroup:
    outline = m.RoundedRectangle(
        width=2.75,
        height=0.52,
        corner_radius=0.24,
        color=color,
        fill_color=PANEL_ALT,
        fill_opacity=1,
        stroke_width=2,
    )
    action_label = code_label_text(label, 20)
    action_label.move_to(outline)
    return m.VGroup(outline, action_label)


def timeline_marker(
    x: float,
    symbol: str,
    kind: str,
    event_name: str,
    color: str,
    square: bool = False,
) -> m.VGroup:
    shape: m.Mobject
    if square:
        shape = m.Square(side_length=0.43, color=color, fill_color=BG, fill_opacity=1)
    else:
        shape = m.Circle(radius=0.23, color=color, fill_color=BG, fill_opacity=1)
    symbol_label = label_text(symbol, 18, color).move_to(shape)
    marker = m.VGroup(shape, symbol_label).move_to([x, -1.1, 0])
    kind_label = label_text(kind, 16, color)
    event_label = code_text(event_name, 18)
    labels = m.VGroup(kind_label, event_label).arrange(m.DOWN, buff=0.05)
    labels.next_to(marker, m.DOWN, buff=0.14)
    return m.VGroup(marker, labels)


def flow_token(color: str, start: list[float]) -> m.Dot:
    return m.Dot(start, radius=0.13, color=color)


class OtelSlackIntegration(m.Scene):
    """Show one stored user span, its events, cleanup, and the linked-span option."""

    def send_event(self, token: m.Dot) -> None:
        self.play(token.animate.move_to([-3.45, 1.38, 0]), run_time=0.42)
        self.play(token.animate.move_to([0.62, 1.38, 0]), run_time=0.42)
        self.play(m.FadeOut(token), run_time=0.18)

    def construct(self) -> None:
        title = heading_text("A Slack interaction as one OpenTelemetry span", 39)
        title.to_edge(m.UP, buff=0.25)
        subtitle = body_text(
            "Global middleware keeps one active span per user", 22, MUTED
        )
        subtitle.next_to(title, m.DOWN, buff=0.13)

        user = labelled_box("USER", "Aiman", 2.2, CYAN).move_to([-5.45, 1.38, 0])
        middleware = labelled_box(
            "GLOBAL MIDDLEWARE", "getUserSpan()", 3.65, PURPLE, detail_is_code=True
        ).move_to([-1.38, 1.38, 0])
        store_outline = box(2.45, 1.15, GREEN).move_to([3.78, 1.38, 0])
        store_title = code_label_text("spanStore", 22, GREEN).move_to(
            [3.78, 1.62, 0]
        )
        store_status = label_text("EMPTY", 22, MUTED).move_to([3.78, 1.18, 0])
        store = m.VGroup(store_outline, store_title)

        first_arrow = m.Arrow(user, middleware, buff=0.18, color=LINE, stroke_width=3)
        second_arrow = m.Arrow(
            middleware, store_outline, buff=0.18, color=LINE, stroke_width=3
        )

        self.play(m.FadeIn(title), m.FadeIn(subtitle, shift=0.1 * m.UP), run_time=0.8)
        self.play(
            m.FadeIn(user),
            m.FadeIn(middleware),
            m.FadeIn(store),
            m.FadeIn(store_status),
            m.GrowArrow(first_arrow),
            m.GrowArrow(second_arrow),
            run_time=0.85,
        )

        current_action = action_chip("first_user_event", CYAN).move_to([-5.45, 0.38, 0])
        self.play(m.FadeIn(current_action, shift=0.1 * m.UP), run_time=0.38)
        token = flow_token(CYAN, [-4.0, 0.38, 0])
        self.play(m.FadeIn(token), run_time=0.18)
        self.send_event(token)

        callout = inline_text(
            [
                ("No span found  →  ", False),
                ("startSpan()", True),
                (" + store it", False),
            ],
            24,
            CYAN,
        )
        callout.move_to([0, 0.27, 0])

        span_panel = box(12.55, 1.95, CYAN).move_to([0, -1.1, 0])
        span_name = code_text("user: aiman", 23).move_to([-4.9, -0.42, 0])
        span_state = label_text("OPEN", 20, GREEN).move_to([4.92, -0.42, 0])
        span_header = m.VGroup(span_name)
        span_line = m.Line(
            [-4.35, -1.1, 0], [-3.62, -1.1, 0], color=CYAN, stroke_width=5
        )
        first_marker = timeline_marker(
            -4.35, "S", "START", "first_user_event", CYAN
        )
        active_status = label_text("1 ACTIVE", 22, GREEN).move_to(store_status)
        self.play(
            m.FadeIn(callout, shift=0.1 * m.UP),
            m.Create(span_panel),
            m.FadeIn(span_header),
            m.FadeIn(span_state),
            m.Create(span_line),
            m.GrowFromCenter(first_marker),
            m.FadeOut(store_status),
            run_time=0.65,
        )
        self.play(m.FadeIn(active_status), run_time=0.25)
        store_status = active_status
        self.wait(0.55)

        next_action = action_chip("select_project", YELLOW).move_to(current_action)
        next_callout = inline_text(
            [("Span found  →  reuse span + ", False), ("addEvent()", True)],
            24,
            YELLOW,
        )
        next_callout.move_to(callout)
        self.play(
            m.FadeOut(current_action), m.FadeOut(callout), run_time=0.16
        )
        self.play(
            m.FadeIn(next_action), m.FadeIn(next_callout), run_time=0.26
        )
        current_action = next_action
        callout = next_callout
        token = flow_token(YELLOW, [-4.0, 0.38, 0])
        self.play(m.FadeIn(token), run_time=0.15)
        self.send_event(token)
        second_marker = timeline_marker(-1.35, "E", "EVENT", "select_project", YELLOW)
        longer_line = m.Line(
            [-4.35, -1.1, 0], [-0.98, -1.1, 0], color=CYAN, stroke_width=5
        )
        self.play(
            m.Transform(span_line, longer_line),
            m.GrowFromCenter(second_marker),
            run_time=0.72,
        )
        self.wait(0.45)

        confirm_action = action_chip("confirm_request", PURPLE).move_to(current_action)
        confirm_callout = body_text(
            "Same span  →  append another named event", 24, PURPLE
        )
        confirm_callout.move_to(callout)
        self.play(
            m.FadeOut(current_action), m.FadeOut(callout), run_time=0.16
        )
        self.play(
            m.FadeIn(confirm_action), m.FadeIn(confirm_callout), run_time=0.26
        )
        current_action = confirm_action
        callout = confirm_callout
        token = flow_token(PURPLE, [-4.0, 0.38, 0])
        self.play(m.FadeIn(token), run_time=0.15)
        self.send_event(token)
        third_marker = timeline_marker(1.35, "E", "EVENT", "confirm_request", PURPLE)
        longer_line = m.Line(
            [-4.35, -1.1, 0], [1.72, -1.1, 0], color=CYAN, stroke_width=5
        )
        self.play(
            m.Transform(span_line, longer_line),
            m.GrowFromCenter(third_marker),
            run_time=0.72,
        )
        self.wait(0.45)

        finish_action = action_chip("finishing_event", CORAL).move_to(current_action)
        finish_callout = inline_text(
            [
                ("finishing_event", True),
                ("  →  call ", False),
                ("span.end()", True),
            ],
            24,
            CORAL,
        )
        finish_callout.move_to(callout)
        self.play(
            m.FadeOut(current_action), m.FadeOut(callout), run_time=0.16
        )
        self.play(
            m.FadeIn(finish_action), m.FadeIn(finish_callout), run_time=0.26
        )
        current_action = finish_action
        callout = finish_callout
        token = flow_token(CORAL, [-4.0, 0.38, 0])
        self.play(m.FadeIn(token), run_time=0.15)
        self.send_event(token)
        finish_marker = timeline_marker(
            4.35, "F", "FINISH", "finishing_event", CORAL, square=True
        )
        final_line = m.Line(
            [-4.35, -1.1, 0], [4.35, -1.1, 0], color=CYAN, stroke_width=5
        )
        ended_state = label_text("ENDED", 20, CORAL).move_to(span_state)
        self.play(
            m.Transform(span_line, final_line),
            m.GrowFromCenter(finish_marker),
            m.FadeOut(span_state),
            run_time=0.5,
        )
        self.play(m.FadeIn(ended_state), run_time=0.25)
        span_state = ended_state
        remove_callout = inline_text(
            [("Then remove the ended span from ", False), ("spanStore", True)],
            24,
            GREEN,
        )
        remove_callout.move_to(callout)
        empty_status = label_text("EMPTY", 22, MUTED).move_to(store_status)
        self.play(
            m.FadeOut(callout),
            m.FadeOut(store_status),
            run_time=0.18,
        )
        self.play(
            m.FadeIn(remove_callout),
            m.FadeIn(empty_status),
            run_time=0.37,
        )
        callout = remove_callout
        store_status = empty_status
        self.play(
            m.FadeOut(span_panel),
            m.FadeOut(span_header),
            m.FadeOut(span_state),
            m.FadeOut(span_line),
            m.FadeOut(first_marker),
            m.FadeOut(second_marker),
            m.FadeOut(third_marker),
            m.FadeOut(finish_marker),
            run_time=0.72,
        )
        self.wait(0.5)

        top_scene = m.VGroup(
            subtitle,
            user,
            middleware,
            store,
            store_status,
            first_arrow,
            second_arrow,
            current_action,
            callout,
        )
        alternative_title = heading_text(
            "Alternative: linked spans for each Slack action", 39
        )
        alternative_title.move_to(title)
        self.play(
            m.FadeOut(title),
            m.FadeOut(top_scene),
            run_time=0.42,
        )
        self.play(m.FadeIn(alternative_title), run_time=0.3)

        current_label = label_text("CURRENT  •  ONE LONG SPAN", 20, CYAN)
        current_label.move_to([-4.65, 1.95, 0])
        long_line = m.Line([-4.9, 1.05, 0], [4.9, 1.05, 0], color=CYAN, stroke_width=6)
        long_start = m.Circle(radius=0.21, color=CYAN, fill_color=BG, fill_opacity=1)
        long_start.move_to([-4.9, 1.05, 0])
        long_end = m.Square(side_length=0.4, color=CORAL, fill_color=BG, fill_opacity=1)
        long_end.move_to([4.9, 1.05, 0])
        wait_one = body_text("user wait included", 20, MUTED).move_to(
            [-2.2, 1.46, 0]
        )
        wait_two = body_text("user wait included", 20, MUTED).move_to(
            [2.0, 1.46, 0]
        )
        long_caption = body_text(
            "Span duration mixes bot work with time between clicks", 23
        )
        long_caption.move_to([0, 0.46, 0])
        self.play(
            m.FadeIn(current_label),
            m.Create(long_line),
            m.GrowFromCenter(long_start),
            m.GrowFromCenter(long_end),
            m.FadeIn(wait_one),
            m.FadeIn(wait_two),
            m.FadeIn(long_caption),
            run_time=0.9,
        )

        linked_label = label_text(
            "ARTICLE ALTERNATIVE  •  LINKED ACTION SPANS", 20, GREEN
        )
        linked_label.move_to([-3.45, -0.08, 0])
        linked_spans = []
        centers = [-4.35, 0, 4.35]
        details = ["first action", "next action", "finish action"]
        colors = [CYAN, PURPLE, CORAL]
        for index, (x, detail, color) in enumerate(zip(centers, details, colors), start=1):
            item = labelled_box(f"SPAN {index}", detail, 2.55, color)
            item.move_to([x, -1.0, 0])
            linked_spans.append(item)
        link_one = m.Arrow(
            linked_spans[0], linked_spans[1], buff=0.18, color=GREEN, stroke_width=3
        )
        link_two = m.Arrow(
            linked_spans[1], linked_spans[2], buff=0.18, color=GREEN, stroke_width=3
        )
        self.play(m.FadeIn(linked_label), run_time=0.3)
        self.play(
            m.LaggedStart(
                *[m.FadeIn(item, shift=0.12 * m.UP) for item in linked_spans],
                lag_ratio=0.18,
            ),
            m.GrowArrow(link_one),
            m.GrowArrow(link_two),
            run_time=1.0,
        )
        conclusion_box = box(10.7, 0.5, GREEN).move_to([0, -1.95, 0])
        conclusion = result_text(
            "Each span measures bot work — not time waiting for the next click", 20
        ).move_to(conclusion_box)
        self.play(m.Create(conclusion_box), m.FadeIn(conclusion), run_time=0.65)
        self.wait(1.8)
