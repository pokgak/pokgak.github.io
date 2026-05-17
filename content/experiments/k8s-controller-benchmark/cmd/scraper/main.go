// scraper polls a controller-runtime /metrics endpoint at a fixed interval
// and writes one CSV row per tick to a file. Run one scraper per controller variant.
//
// Usage:
//
//	scraper --url http://localhost:19090/metrics \
//	        --output metrics-good-N1000.csv \
//	        --controller good \
//	        --interval 1s
package main

import (
	"encoding/csv"
	"flag"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	dto "github.com/prometheus/client_model/go"
	"github.com/prometheus/common/expfmt"
)

func main() {
	url := flag.String("url", "http://localhost:19090/metrics", "metrics endpoint URL")
	output := flag.String("output", "metrics.csv", "output CSV file path")
	controller := flag.String("controller", "unknown", "controller name label for the CSV")
	interval := flag.Duration("interval", time.Second, "scrape interval")
	flag.Parse()

	f, err := os.Create(*output)
	if err != nil {
		log.Fatalf("create %s: %v", *output, err)
	}
	defer f.Close()

	w := csv.NewWriter(f)
	if err := w.Write([]string{
		"timestamp", "controller",
		"queue_depth", "queue_adds_total", "queue_retries_total",
		"reconcile_success_total", "reconcile_error_total", "reconcile_requeue_total",
		"active_workers", "unfinished_work_s",
		"reconcile_latency_sum", "reconcile_latency_count",
	}); err != nil {
		log.Fatalf("write header: %v", err)
	}
	w.Flush()

	client := &http.Client{Timeout: 3 * time.Second}
	ticker := time.NewTicker(*interval)
	defer ticker.Stop()

	// controller-runtime uses lowercase Kind as both the controller label
	// and the workqueue name label.
	const kind = "widget"

	for ts := range ticker.C {
		families, err := scrape(client, *url)
		if err != nil {
			// controller may not be ready yet — skip row, don't die
			log.Printf("warn: scrape %s: %v", *url, err)
			continue
		}

		latSum, latCount := histogram(families, "controller_runtime_reconcile_time_seconds",
			map[string]string{"controller": kind})

		row := []string{
			ts.UTC().Format(time.RFC3339Nano),
			*controller,
			ff(gauge(families, "workqueue_depth", map[string]string{"name": kind})),
			ff(counter(families, "workqueue_adds_total", map[string]string{"name": kind})),
			ff(counter(families, "workqueue_retries_total", map[string]string{"name": kind})),
			ff(counter(families, "controller_runtime_reconcile_total", map[string]string{"controller": kind, "result": "success"})),
			ff(counter(families, "controller_runtime_reconcile_total", map[string]string{"controller": kind, "result": "error"})),
			ff(counter(families, "controller_runtime_reconcile_total", map[string]string{"controller": kind, "result": "requeue"})),
			ff(gauge(families, "controller_runtime_active_workers", map[string]string{"controller": kind})),
			ff(gauge(families, "workqueue_unfinished_work_seconds", map[string]string{"name": kind})),
			ff(latSum),
			ff(latCount),
		}
		if err := w.Write(row); err != nil {
			log.Printf("write row: %v", err)
		}
		w.Flush()
	}
}

func scrape(c *http.Client, url string) (map[string]*dto.MetricFamily, error) {
	resp, err := c.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	var p expfmt.TextParser
	// TextToMetricFamilies returns partial results + error; use both.
	fams, _ := p.TextToMetricFamilies(strings.NewReader(string(body)))
	return fams, nil
}

func gauge(fams map[string]*dto.MetricFamily, name string, want map[string]string) float64 {
	fam, ok := fams[name]
	if !ok {
		return 0
	}
	for _, m := range fam.Metric {
		if labelsMatch(m, want) && m.Gauge != nil {
			return m.Gauge.GetValue()
		}
	}
	return 0
}

func counter(fams map[string]*dto.MetricFamily, name string, want map[string]string) float64 {
	fam, ok := fams[name]
	if !ok {
		return 0
	}
	for _, m := range fam.Metric {
		if labelsMatch(m, want) && m.Counter != nil {
			return m.Counter.GetValue()
		}
	}
	return 0
}

func histogram(fams map[string]*dto.MetricFamily, name string, want map[string]string) (float64, float64) {
	fam, ok := fams[name]
	if !ok {
		return 0, 0
	}
	for _, m := range fam.Metric {
		if labelsMatch(m, want) && m.Histogram != nil {
			return m.Histogram.GetSampleSum(), float64(m.Histogram.GetSampleCount())
		}
	}
	return 0, 0
}

func labelsMatch(m *dto.Metric, want map[string]string) bool {
	for k, v := range want {
		found := false
		for _, lp := range m.Label {
			if lp.GetName() == k && lp.GetValue() == v {
				found = true
				break
			}
		}
		if !found {
			return false
		}
	}
	return true
}

func ff(v float64) string {
	return strconv.FormatFloat(v, 'f', 4, 64)
}
