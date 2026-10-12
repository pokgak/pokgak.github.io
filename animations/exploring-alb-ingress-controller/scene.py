"""Visualise the routing and cost trade-off discussed in the ALB for EKS article."""

import manimgx as m


m.config.pixel_width = 1280
m.config.pixel_height = 720
m.config.frame_rate = 30
m.config.background_color = "#08111F"

BG = "#08111F"
PANEL = "#101D2F"
PANEL_LIGHT = "#17263B"
WHITE = "#F8FAFC"
MUTED = "#A8B4C5"
AWS_ORANGE = "#FF9900"
NGINX_BLUE = "#38BDF8"
ROUTE_GREEN = "#34D399"
NLB_BLUE = "#60A5FA"


def text(
    value: str,
    size: int,
    color: str = WHITE,
    *,
    weight: str = m.NORMAL,
    font: str = "sans-serif",
) -> m.Text:
    return m.Text(
        value,
        font=font,
        font_size=size,
        color=color,
        weight=weight,
    )


def body_text(value: str, size: int, color: str = WHITE) -> m.Text:
    return text(value, size, color, weight=m.NORMAL)


def label_text(value: str, size: int, color: str = WHITE) -> m.Text:
    return text(value, size, color, weight=m.MEDIUM)


def heading_text(value: str, size: int, color: str = WHITE) -> m.Text:
    return text(value, size, color, weight=m.SEMIBOLD)


def code_text(value: str, size: int, color: str = WHITE) -> m.Text:
    return text(value, size, color, weight=m.MEDIUM, font="monospace")


def node(
    title: str,
    subtitle: str,
    center: list[float],
    width: float,
    height: float,
    accent: str,
) -> m.VGroup:
    body = m.RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.14,
        stroke_color=accent,
        stroke_width=2.5,
        fill_color=PANEL,
        fill_opacity=1,
    )
    copy = m.VGroup(label_text(title, 25), body_text(subtitle, 18, MUTED)).arrange(
        m.DOWN, buff=0.08
    )
    return m.VGroup(body, copy).move_to(center)


def service_node(name: str, center: list[float]) -> m.VGroup:
    body = m.RoundedRectangle(
        width=2.15,
        height=0.52,
        corner_radius=0.12,
        stroke_color=ROUTE_GREEN,
        stroke_width=2,
        fill_color=PANEL,
        fill_opacity=1,
    )
    return m.VGroup(body, label_text(name, 21)).move_to(center)


def pod_node(name: str, center: list[float]) -> m.VGroup:
    body = m.RoundedRectangle(
        width=1.75,
        height=0.52,
        corner_radius=0.12,
        stroke_color=NGINX_BLUE,
        stroke_width=2,
        fill_color=PANEL,
        fill_opacity=1,
    )
    return m.VGroup(body, label_text(name, 21)).move_to(center)


def route_arrow(start: list[float], end: list[float], color: str = MUTED) -> m.Arrow:
    return m.Arrow(start, end, buff=0, color=color, stroke_width=2.5)


def info_card(
    eyebrow: str,
    main_lines: list[tuple[str, int, str, str]],
    center: list[float],
) -> m.VGroup:
    body = m.RoundedRectangle(
        width=4.05,
        height=3.55,
        corner_radius=0.2,
        stroke_color="#29415F",
        stroke_width=2,
        fill_color=PANEL,
        fill_opacity=1,
    )
    heading = label_text(eyebrow, 19, AWS_ORANGE).move_to([0, 1.28, 0])
    lines = m.VGroup(
        *[
            text(line, size, color, weight=weight)
            for line, size, color, weight in main_lines
        ]
    ).arrange(m.DOWN, buff=0.19)
    lines.move_to([0, -0.12, 0])
    return m.VGroup(body, heading, lines).move_to(center)


class EksIngressTradeoff(m.Scene):
    def construct(self) -> None:
        current_title = heading_text("Current path: routing inside EKS", 34).move_to(
            [0, 3.42, 0]
        )
        current_subtitle = body_text(
            "NLB passes connections to ingress-nginx, which selects a backend",
            21,
            MUTED,
        ).move_to([0, 2.94, 0])
        current_header = m.VGroup(current_title, current_subtitle)

        internet_ring = m.Circle(
            radius=0.48,
            color=MUTED,
            stroke_width=2,
            fill_color=PANEL_LIGHT,
            fill_opacity=1,
        )
        internet_icon = label_text("WWW", 17, WHITE).move_to(internet_ring)
        internet_label = label_text("Internet", 20, MUTED).next_to(
            internet_ring, m.DOWN, buff=0.16
        )
        internet = m.VGroup(internet_ring, internet_icon, internet_label).move_to(
            [-6.1, 0.18, 0]
        )

        nlb = node("NLB", "L4 pass-through", [-4.25, 0.45, 0], 1.95, 1.3, NLB_BLUE)

        nginx_label = label_text("ingress-nginx", 22, NGINX_BLUE).move_to(
            [-1.45, 1.87, 0]
        )
        nginx_pods = m.VGroup(
            pod_node("pod 1", [-1.45, 1.12, 0]),
            pod_node("pod 2", [-1.45, 0.38, 0]),
            pod_node("pod 3", [-1.45, -0.36, 0]),
        )
        routing_note = body_text("host + path routing", 18, MUTED).move_to(
            [-1.45, -1.02, 0]
        )
        nginx_column = m.VGroup(nginx_label, nginx_pods, routing_note)

        backend_label = label_text("Backend services", 22, ROUTE_GREEN).move_to(
            [4.82, 2.02, 0]
        )
        backend_y = [1.35, 0.68, 0.01, -0.66, -1.33]
        backends = m.VGroup(
            *[
                service_node(f"Service {letter}", [4.82, y, 0])
                for letter, y in zip("ABCDE", backend_y)
            ]
        )
        backend_column = m.VGroup(backend_label, backends)

        internet_to_nlb = route_arrow([-5.56, 0.45, 0], [-5.29, 0.45, 0], NLB_BLUE)
        nlb_to_nginx = route_arrow([-3.21, 0.45, 0], [-2.38, 0.45, 0], NGINX_BLUE)
        nginx_to_backends = m.VGroup(
            *[
                route_arrow([-0.52, 0.38, 0], [3.68, y, 0], ROUTE_GREEN)
                for y in backend_y
            ]
        )
        current_arrows = m.VGroup(internet_to_nlb, nlb_to_nginx, nginx_to_backends)

        self.play(m.FadeIn(current_header, shift=0.15 * m.DOWN), run_time=0.7)
        self.play(
            m.LaggedStart(
                m.FadeIn(internet),
                m.FadeIn(nlb),
                m.FadeIn(nginx_column),
                m.FadeIn(backend_column),
                lag_ratio=0.12,
            ),
            run_time=1.35,
        )
        self.play(
            m.LaggedStart(
                m.Create(internet_to_nlb),
                m.Create(nlb_to_nginx),
                *[m.Create(arrow) for arrow in nginx_to_backends],
                lag_ratio=0.08,
            ),
            run_time=1.2,
        )

        request_caption = m.VGroup(
            label_text("request", 21, AWS_ORANGE),
            code_text("/orders", 21, AWS_ORANGE),
        ).arrange(m.RIGHT, buff=0.14)
        request_caption.move_to([-4.02, -2.42, 0])
        packet = m.Dot([-5.55, 0.45, 0], radius=0.11, color=AWS_ORANGE)
        self.play(m.FadeIn(request_caption), m.FadeIn(packet), run_time=0.35)
        self.play(
            packet.animate.move_to([-0.45, 0.38, 0]),
            m.Circumscribe(nginx_pods[1], color=NGINX_BLUE),
            run_time=1.35,
            rate_func=m.linear,
        )
        self.play(
            packet.animate.move_to([3.63, 0.01, 0]),
            m.Circumscribe(backends[2], color=ROUTE_GREEN),
            run_time=1.15,
            rate_func=m.linear,
        )
        self.play(m.FadeOut(packet), m.FadeOut(request_caption), run_time=0.3)
        self.wait(0.45)

        direct_title = heading_text(
            "ALB path: listener rules select targets", 34
        ).move_to([0, 3.42, 0])
        direct_subtitle = body_text(
            "Application routing moves into the load balancer",
            21,
            MUTED,
        ).move_to([0, 2.94, 0])
        direct_header = m.VGroup(direct_title, direct_subtitle)

        alb_body = m.RoundedRectangle(
            width=3.75,
            height=3.62,
            corner_radius=0.18,
            stroke_color=AWS_ORANGE,
            stroke_width=3,
            fill_color=PANEL,
            fill_opacity=1,
        ).move_to([-2.15, 0.28, 0])
        alb_title = label_text("ALB", 28, AWS_ORANGE).move_to([-2.15, 1.68, 0])
        alb_subtitle = body_text("L7 listener rules", 19, MUTED).move_to(
            [-2.15, 1.25, 0]
        )
        rule_specs = [
            ("/api/*  →  Service A", 0.58),
            ("/orders/*  →  Service C", -0.08),
            ("default  →  Service E", -0.74),
        ]
        rule_rows = m.VGroup()
        for rule_text, y in rule_specs:
            rule_body = m.RoundedRectangle(
                width=3.25,
                height=0.5,
                corner_radius=0.08,
                stroke_color="#35506E",
                stroke_width=1.5,
                fill_color=PANEL_LIGHT,
                fill_opacity=1,
            ).move_to([-2.15, y, 0])
            rule_rows.add(
                m.VGroup(rule_body, code_text(rule_text, 18).move_to(rule_body))
            )
        alb = m.VGroup(alb_body, alb_title, alb_subtitle, rule_rows)

        direct_targets = [backend_y[0], backend_y[2], backend_y[4]]
        direct_arrows = m.VGroup(
            *[
                route_arrow([-0.22, rule_y, 0], [3.68, target_y, 0], ROUTE_GREEN)
                for (_, rule_y), target_y in zip(rule_specs, direct_targets)
            ]
        )
        internet_to_alb = route_arrow([-5.56, 0.45, 0], [-4.08, 0.45, 0], AWS_ORANGE)
        no_hop = m.VGroup(
            m.RoundedRectangle(
                width=2.75,
                height=0.48,
                corner_radius=0.14,
                stroke_color=ROUTE_GREEN,
                fill_color="#0E342B",
                fill_opacity=1,
                stroke_width=1.5,
            ),
            label_text("no ingress-nginx hop", 18, ROUTE_GREEN),
        ).move_to([-2.15, -1.87, 0])

        self.play(
            m.ReplacementTransform(current_header, direct_header),
            m.FadeOut(current_arrows),
            m.FadeOut(nginx_column),
            m.ReplacementTransform(nlb, alb),
            run_time=1.45,
        )
        self.play(
            m.Create(internet_to_alb),
            m.LaggedStart(
                *[m.Create(arrow) for arrow in direct_arrows], lag_ratio=0.14
            ),
            m.FadeIn(no_hop, shift=0.12 * m.UP),
            run_time=1.15,
        )

        for index, target_y in enumerate(direct_targets):
            rule_y = rule_specs[index][1]
            routed_packet = m.Dot([-5.53, 0.45, 0], radius=0.1, color=AWS_ORANGE)
            self.play(m.FadeIn(routed_packet), run_time=0.12)
            self.play(
                routed_packet.animate.move_to([-0.1, rule_y, 0]),
                m.Circumscribe(rule_rows[index], color=AWS_ORANGE),
                run_time=0.7,
                rate_func=m.linear,
            )
            self.play(
                routed_packet.animate.move_to([3.63, target_y, 0]),
                m.Circumscribe(backends[index * 2], color=ROUTE_GREEN),
                run_time=0.65,
                rate_func=m.linear,
            )
            self.play(m.FadeOut(routed_packet), run_time=0.12)

        self.wait(0.45)

        topology = m.VGroup(
            direct_header,
            internet,
            alb,
            backend_column,
            internet_to_alb,
            direct_arrows,
            no_hop,
        )
        tradeoff_title = heading_text("The trade-off", 36).move_to([0, 3.42, 0])
        tradeoff_subtitle = body_text(
            "Direct routing changes the bottleneck — not the economics",
            21,
            MUTED,
        ).move_to([0, 2.92, 0])
        self.play(
            m.FadeOut(topology),
            m.FadeIn(m.VGroup(tradeoff_title, tradeoff_subtitle)),
            run_time=0.85,
        )

        path_card = info_card(
            "PATH",
            [
                ("ALB  →  backends", 29, ROUTE_GREEN, m.SEMIBOLD),
                ("No ingress-nginx hop", 21, WHITE, m.NORMAL),
                ("Simpler request path", 20, MUTED, m.NORMAL),
            ],
            [-4.35, 0.45, 0],
        )
        rules_card = info_card(
            "LISTENER RULES",
            [
                ("100 / ALB", 31, AWS_ORANGE, m.SEMIBOLD),
                ("soft quota", 20, MUTED, m.NORMAL),
                ("10 free rules", 21, WHITE, m.MEDIUM),
                ("then evaluations count", 19, MUTED, m.NORMAL),
            ],
            [0, 0.45, 0],
        )
        connections_card = info_card(
            "TLS CONNECTIONS / LCU",
            [
                ("NLB   50/s", 26, NLB_BLUE, m.SEMIBOLD),
                ("ALB   25/s", 26, AWS_ORANGE, m.SEMIBOLD),
                ("Article estimate", 19, MUTED, m.NORMAL),
                ("ALB: 2.7× / connection", 20, WHITE, m.BOLD),
            ],
            [4.35, 0.45, 0],
        )
        cards = m.VGroup(path_card, rules_card, connections_card)
        self.play(
            m.LaggedStart(*[m.FadeIn(card, shift=0.15 * m.UP) for card in cards], lag_ratio=0.15),
            run_time=1.25,
        )

        billing_note = body_text(
            "LCU billing uses the highest usage dimension",
            20,
            MUTED,
        ).move_to([0, -1.82, 0])
        conclusion = heading_text(
            "Choose for your workload  •  simpler path ≠ lower cost",
            25,
            WHITE,
        ).move_to([0, -2.36, 0])
        self.play(m.FadeIn(billing_note), m.FadeIn(conclusion), run_time=0.7)
        self.wait(2.0)
