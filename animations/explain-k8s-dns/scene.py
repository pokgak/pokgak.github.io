"""Animate a Kubernetes Service request from DNS lookup through reverse NAT."""

import manimgx as m


m.config.background_color = "#08111F"

BACKGROUND = "#08111F"
PANEL = "#111E32"
PANEL_ALT = "#172640"
TEXT = "#F8FAFC"
MUTED = "#CBD5E1"
BLUE = "#38BDF8"
PURPLE = "#A78BFA"
ORANGE = "#FB923C"
GREEN = "#4ADE80"
LINE = "#52627A"


def card(
    title: str,
    subtitle: str,
    *,
    width: float,
    height: float = 1.8,
    accent: str = BLUE,
    title_size: int = 31,
    subtitle_size: int = 25,
    subtitle_font: str = "sans-serif",
) -> m.VGroup:
    """Build a labelled card with a colored top edge."""
    background = m.RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.16,
        color=LINE,
        fill_color=PANEL,
        fill_opacity=1,
        stroke_width=2,
    )
    top_edge = m.Line(
        [-width / 2 + 0.18, height / 2 - 0.12, 0],
        [width / 2 - 0.18, height / 2 - 0.12, 0],
        color=accent,
        stroke_width=5,
    )
    heading = m.Text(
        title,
        font="sans-serif",
        weight=m.MEDIUM,
        font_size=title_size,
        color=TEXT,
    )
    detail = m.Text(
        subtitle,
        font=subtitle_font,
        weight=m.MEDIUM,
        font_size=subtitle_size,
        color=MUTED,
    )
    labels = m.VGroup(heading, detail).arrange(m.DOWN, buff=0.16)
    labels.shift(0.04 * m.DOWN)
    return m.VGroup(background, top_edge, labels)


def pill(
    label: str,
    *,
    width: float,
    accent: str,
    font_size: int = 30,
) -> m.VGroup:
    """Build a compact label used for DNS names and packet headers."""
    background = m.RoundedRectangle(
        width=width,
        height=0.88,
        corner_radius=0.22,
        color=accent,
        fill_color=PANEL_ALT,
        fill_opacity=1,
        stroke_width=2,
    )
    text = m.Text(
        label,
        font="monospace",
        weight=m.MEDIUM,
        font_size=font_size,
        color=TEXT,
    )
    return m.VGroup(background, text)


def stage(number: str, label: str, color: str) -> m.VGroup:
    """Build the stage marker shown below the persistent title."""
    number_badge = m.Circle(
        radius=0.27,
        color=color,
        fill_color=color,
        fill_opacity=1,
        stroke_width=0,
    )
    number_text = m.Text(
        number,
        font="sans-serif",
        weight=m.MEDIUM,
        font_size=24,
        color=BACKGROUND,
    ).move_to(number_badge)
    label_text = m.Text(
        label,
        font="sans-serif",
        weight=m.SEMIBOLD,
        font_size=28,
        color=color,
    )
    marker = m.VGroup(m.VGroup(number_badge, number_text), label_text)
    marker.arrange(m.RIGHT, buff=0.22)
    marker.move_to([0, 2.62, 0])
    return marker


def route_arrows(color: str, *, reverse: bool = False) -> m.VGroup:
    """Build the two packet-path arrows over the three network actors."""
    y = 1.32
    if reverse:
        first = m.Arrow([4.72, y, 0], [0.32, y, 0], buff=0, color=color, stroke_width=4)
        second = m.Arrow([-0.32, y, 0], [-4.72, y, 0], buff=0, color=color, stroke_width=4)
    else:
        first = m.Arrow([-4.72, y, 0], [-0.32, y, 0], buff=0, color=color, stroke_width=4)
        second = m.Arrow([0.32, y, 0], [4.72, y, 0], buff=0, color=color, stroke_width=4)
    return m.VGroup(first, second)


class KubernetesDnsJourney(m.Scene):
    """Show how a short Service name becomes a request to a Pod and back."""

    def construct(self) -> None:
        title = m.Text(
            "Kubernetes DNS: from bar to a Pod and back",
            font="sans-serif",
            weight=m.SEMIBOLD,
            font_size=38,
            color=TEXT,
        ).move_to([0, 3.45, 0])
        title_rule = m.Line(
            [-6.1, 3.05, 0],
            [6.1, 3.05, 0],
            color=LINE,
            stroke_width=2,
        )
        self.play(m.FadeIn(title, shift=0.15 * m.DOWN), m.Create(title_rule), run_time=0.7)

        # 1. The application starts with only the short Service name.
        current_stage = stage("1", "SHORT SERVICE NAME", BLUE)
        source = card(
            "foo Pod",
            "namespace  app",
            width=2.8,
            accent=BLUE,
            subtitle_font="monospace",
        ).move_to([-4.6, 0.2, 0])
        request = pill("GET  https://bar/", width=5.2, accent=BLUE, font_size=35).move_to([2.2, 0.2, 0])
        request_arrow = m.Arrow(
            [-3.05, 0.2, 0],
            [-0.65, 0.2, 0],
            buff=0,
            color=LINE,
            stroke_width=4,
        )
        short_name = m.Text(
            "The application knows only the Service name:  bar",
            font="sans-serif",
            weight=m.NORMAL,
            font_size=29,
            color=MUTED,
        ).move_to([0, -2.05, 0])
        stage_one = m.VGroup(source, request_arrow, request, short_name)
        self.play(m.FadeIn(current_stage), m.FadeIn(source), run_time=0.6)
        self.play(m.Create(request_arrow), m.FadeIn(request, shift=0.25 * m.RIGHT), run_time=0.8)
        self.play(m.FadeIn(short_name), m.Indicate(request, color=BLUE), run_time=0.8)
        self.wait(1.0)

        # 2. The resolver appends the Pod's namespace search domain.
        next_stage = stage("2", "SEARCH-DOMAIN EXPANSION", PURPLE)
        self.play(
            m.FadeOut(stage_one),
            m.FadeOut(current_stage),
            m.FadeIn(next_stage),
            run_time=0.55,
        )
        current_stage = next_stage
        resolver_box = m.RoundedRectangle(
            width=12.2,
            height=3.25,
            corner_radius=0.18,
            color=LINE,
            fill_color=PANEL,
            fill_opacity=1,
            stroke_width=2,
        ).move_to([0, -0.05, 0])
        resolver_title = m.Text(
            "/etc/resolv.conf",
            font="monospace",
            weight=m.MEDIUM,
            font_size=29,
            color=TEXT,
        ).move_to([0, 1.02, 0])
        search_domain = m.Text(
            "search  app.svc.cluster.local",
            font="monospace",
            weight=m.NORMAL,
            font_size=30,
            color=PURPLE,
        ).move_to([0, 0.42, 0])
        short = pill("bar", width=1.45, accent=BLUE, font_size=32).move_to([-4.55, -0.62, 0])
        expanded = pill(
            "bar.app.svc.cluster.local",
            width=5.25,
            accent=PURPLE,
            font_size=27,
        ).move_to([2.7, -0.62, 0])
        expansion_arrow = m.Arrow(
            [-3.65, -0.62, 0],
            [-0.2, -0.62, 0],
            buff=0,
            color=PURPLE,
            stroke_width=4,
        )
        expansion_label = m.Text(
            "append search domain",
            font="sans-serif",
            weight=m.MEDIUM,
            font_size=25,
            color=MUTED,
        ).move_to([-1.92, -0.18, 0])
        resolver_caption = m.Text(
            "The resolver expands the short name before asking DNS",
            font="sans-serif",
            weight=m.NORMAL,
            font_size=29,
            color=MUTED,
        ).move_to([0, -2.2, 0])
        stage_two = m.VGroup(
            resolver_box,
            resolver_title,
            search_domain,
            short,
            expansion_arrow,
            expansion_label,
            expanded,
            resolver_caption,
        )
        self.play(m.FadeIn(resolver_box), m.FadeIn(resolver_title), m.FadeIn(search_domain), run_time=0.7)
        self.play(m.FadeIn(short), m.Create(expansion_arrow), m.FadeIn(expansion_label), run_time=0.7)
        self.play(m.FadeIn(expanded, shift=0.2 * m.RIGHT), m.FadeIn(resolver_caption), run_time=0.8)
        self.wait(1.2)

        # 3. CoreDNS maps the full name to the Service's stable virtual IP.
        next_stage = stage("3", "SERVICE CLUSTERIP RESOLUTION", PURPLE)
        self.play(
            m.FadeOut(stage_two),
            m.FadeOut(current_stage),
            m.FadeIn(next_stage),
            run_time=0.55,
        )
        current_stage = next_stage
        fqdn = card(
            "DNS query",
            "bar.app.svc.cluster.local",
            width=4.8,
            accent=PURPLE,
            title_size=30,
            subtitle_size=24,
            subtitle_font="monospace",
        ).move_to([-4.55, 0.2, 0])
        coredns = card("CoreDNS", "cluster DNS", width=2.25, accent=PURPLE).move_to([0, 0.2, 0])
        service = card(
            "bar Service",
            "ClusterIP  10.96.0.42",
            width=4.1,
            accent=ORANGE,
            title_size=30,
            subtitle_size=25,
            subtitle_font="monospace",
        ).move_to([4.55, 0.2, 0])
        dns_arrow = m.Arrow([-2.15, 0.2, 0], [-1.28, 0.2, 0], buff=0, color=LINE, stroke_width=4)
        answer_arrow = m.Arrow([1.28, 0.2, 0], [2.55, 0.2, 0], buff=0, color=ORANGE, stroke_width=4)
        virtual_label = m.Text(
            "CoreDNS returns a stable virtual IP for the Service",
            font="sans-serif",
            weight=m.NORMAL,
            font_size=29,
            color=MUTED,
        ).move_to([0, -2.05, 0])
        stage_three = m.VGroup(fqdn, dns_arrow, coredns, answer_arrow, service, virtual_label)
        self.play(m.FadeIn(fqdn), m.Create(dns_arrow), m.FadeIn(coredns), run_time=0.8)
        self.play(m.Create(answer_arrow), m.FadeIn(service, shift=0.2 * m.RIGHT), run_time=0.8)
        self.play(m.FadeIn(virtual_label), m.Indicate(service, color=ORANGE), run_time=0.8)
        self.wait(1.2)

        # Build the shared network view used for the outbound and return packets.
        next_stage = stage("4", "IPTABLES DNAT", ORANGE)
        self.play(
            m.FadeOut(stage_three),
            m.FadeOut(current_stage),
            m.FadeIn(next_stage),
            run_time=0.55,
        )
        current_stage = next_stage
        foo = card(
            "foo Pod",
            "10.244.1.8",
            width=2.7,
            height=1.7,
            accent=BLUE,
            subtitle_font="monospace",
        ).move_to([-5.0, -0.05, 0])
        iptables = card(
            "iptables",
            "kube-proxy rule",
            width=3.4,
            height=1.7,
            accent=ORANGE,
            subtitle_font="monospace",
        ).move_to([0, -0.05, 0])
        bar = card(
            "bar Pod",
            "10.244.2.17",
            width=2.7,
            height=1.7,
            accent=GREEN,
            subtitle_font="monospace",
        ).move_to([5.0, -0.05, 0])
        stems = m.VGroup(
            m.Line([-5.0, 0.82, 0], [-5.0, 1.32, 0], color=LINE, stroke_width=3),
            m.Line([0, 0.82, 0], [0, 1.32, 0], color=LINE, stroke_width=3),
            m.Line([5.0, 0.82, 0], [5.0, 1.32, 0], color=LINE, stroke_width=3),
        )
        outbound_route = route_arrows(ORANGE)
        packet = m.Dot([-5.0, 1.32, 0], radius=0.13, color=ORANGE)
        packet_ring = m.Circle(radius=0.22, color=ORANGE, stroke_width=3).move_to(packet)
        request_header = pill(
            "request destination  ·  10.96.0.42  (ClusterIP)",
            width=10.4,
            accent=ORANGE,
            font_size=28,
        ).move_to([0, -1.75, 0])
        dnat_caption = m.Text(
            "iptables rewrites the destination:  Service IP  →  Pod IP",
            font="sans-serif",
            weight=m.NORMAL,
            font_size=28,
            color=MUTED,
        ).move_to([0, -2.55, 0])
        self.play(
            m.FadeIn(foo),
            m.FadeIn(iptables),
            m.FadeIn(bar),
            m.Create(stems),
            m.Create(outbound_route),
            run_time=0.9,
        )
        self.play(m.FadeIn(packet), m.FadeIn(packet_ring), m.FadeIn(request_header), run_time=0.6)
        self.play(
            packet.animate.move_to([0, 1.32, 0]),
            packet_ring.animate.move_to([0, 1.32, 0]),
            run_time=1.2,
        )
        pod_header = pill(
            "request destination  ·  10.244.2.17  (Pod IP)",
            width=10.4,
            accent=ORANGE,
            font_size=28,
        ).move_to(request_header)
        self.play(
            m.Transform(request_header, pod_header),
            m.Indicate(iptables, color=ORANGE),
            m.FadeIn(dnat_caption),
            run_time=0.9,
        )
        self.wait(0.8)

        # 5. The rewritten request can now be delivered to the selected Pod.
        next_stage = stage("5", "REQUEST DELIVERY", GREEN)
        self.play(m.FadeOut(current_stage), m.FadeIn(next_stage), run_time=0.45)
        current_stage = next_stage
        self.play(
            packet.animate.move_to([5.0, 1.32, 0]),
            packet_ring.animate.move_to([5.0, 1.32, 0]),
            run_time=1.3,
        )
        delivered = pill(
            "request delivered  ·  bar Pod  10.244.2.17",
            width=10.4,
            accent=GREEN,
            font_size=29,
        ).move_to(request_header)
        self.play(
            m.Transform(request_header, delivered),
            m.FadeOut(dnat_caption),
            m.Indicate(bar, color=GREEN),
            run_time=0.9,
        )
        self.wait(1.1)

        # 6. Conntrack applies reverse NAT so foo sees the Service IP it called.
        next_stage = stage("6", "RESPONSE + REVERSE NAT", GREEN)
        self.play(
            m.FadeOut(current_stage),
            m.FadeIn(next_stage),
            m.FadeOut(outbound_route),
            m.FadeOut(packet),
            m.FadeOut(packet_ring),
            run_time=0.5,
        )
        current_stage = next_stage
        return_route = route_arrows(GREEN, reverse=True)
        response_packet = m.Dot([5.0, 1.32, 0], radius=0.13, color=GREEN)
        response_ring = m.Circle(radius=0.22, color=GREEN, stroke_width=3).move_to(response_packet)
        pod_response = pill(
            "response source  ·  10.244.2.17  (Pod IP)",
            width=10.4,
            accent=GREEN,
            font_size=28,
        ).move_to(request_header)
        self.play(
            m.Create(return_route),
            m.FadeIn(response_packet),
            m.FadeIn(response_ring),
            m.Transform(request_header, pod_response),
            run_time=0.8,
        )
        self.play(
            response_packet.animate.move_to([0, 1.32, 0]),
            response_ring.animate.move_to([0, 1.32, 0]),
            run_time=1.2,
        )
        service_response = pill(
            "response source  ·  10.96.0.42  (ClusterIP)",
            width=10.4,
            accent=GREEN,
            font_size=28,
        ).move_to(request_header)
        reverse_caption = m.Text(
            "Reverse NAT restores the Service IP as the response source",
            font="sans-serif",
            weight=m.NORMAL,
            font_size=28,
            color=MUTED,
        ).move_to([0, -2.55, 0])
        self.play(
            m.Transform(request_header, service_response),
            m.Indicate(iptables, color=GREEN),
            m.FadeIn(reverse_caption),
            run_time=0.9,
        )
        self.play(
            response_packet.animate.move_to([-5.0, 1.32, 0]),
            response_ring.animate.move_to([-5.0, 1.32, 0]),
            run_time=1.2,
        )
        complete_stage = stage("✓", "RESPONSE ACCEPTED BY foo", GREEN)
        complete_caption = m.Text(
            "foo receives the reply from the same ClusterIP it called",
            font="sans-serif",
            weight=m.BOLD,
            font_size=29,
            color=TEXT,
        ).move_to([0, -2.55, 0])
        self.play(
            m.FadeOut(current_stage),
            m.FadeIn(complete_stage),
            m.FadeOut(reverse_caption),
            m.FadeIn(complete_caption),
            m.Indicate(foo, color=GREEN),
            run_time=0.9,
        )
        self.wait(2.0)
