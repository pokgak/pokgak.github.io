// GROUP BY key, SUM(amount) over N rows, four ways.
// clang++ -O2 -std=c++20 -march=native groupby.cpp -o groupby
#include <malloc/malloc.h>

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <random>
#include <string>
#include <unordered_map>
#include <vector>

using Clock = std::chrono::steady_clock;

static size_t heap_in_use() {
    malloc_statistics_t s;
    malloc_zone_statistics(nullptr, &s);
    return s.size_in_use;
}

static uint64_t mix(uint64_t x) {
    x ^= x >> 33; x *= 0xff51afd7ed558ccdULL;
    x ^= x >> 33; x *= 0xc4ceb9fe1a85ec53ULL;
    x ^= x >> 33;
    return x;
}

// Open-addressing, linear probing, power-of-two capacity. The "good hash table" case.
struct FlatMap {
    std::vector<uint32_t> keys;
    std::vector<int64_t> vals;
    std::vector<uint8_t> used;
    uint64_t mask;
    explicit FlatMap(size_t n) {
        size_t cap = 1;
        while (cap < n * 2) cap <<= 1;
        keys.resize(cap); vals.resize(cap); used.resize(cap);
        mask = cap - 1;
    }
    void add(uint32_t k, int64_t v) {
        uint64_t i = mix(k) & mask;
        while (used[i] && keys[i] != k) i = (i + 1) & mask;
        if (!used[i]) { used[i] = 1; keys[i] = k; }
        vals[i] += v;
    }
};

template <class F>
static double time_ms(F&& f) {
    auto t0 = Clock::now();
    f();
    return std::chrono::duration<double, std::milli>(Clock::now() - t0).count();
}

template <class F>
static double best_of(int reps, F&& f) {
    double best = 1e18;
    for (int r = 0; r < reps; r++) best = std::min(best, time_ms(f));
    return best;
}

int main() {
    const size_t N = 20'000'000;
    const size_t groups[] = {100, 10'000, 1'000'000, 10'000'000};
    std::mt19937_64 rng(42);

    printf("%-10s %-22s %10s %10s %12s\n", "groups", "method", "ms", "ns/row", "table MB");
    for (size_t G : groups) {
        std::vector<uint32_t> ids(N);
        std::vector<int64_t> amt(N);
        std::uniform_int_distribution<uint32_t> d(0, G - 1);
        for (size_t i = 0; i < N; i++) { ids[i] = d(rng); amt[i] = (int64_t)(rng() % 1000); }

        // String keys, like "user_123456" coming out of JSON / a row store.
        std::vector<std::string> names(G);
        for (size_t g = 0; g < G; g++) names[g] = "user_" + std::to_string(1'000'000'000ULL + g);
        std::vector<const std::string*> skeys(N);
        for (size_t i = 0; i < N; i++) skeys[i] = &names[ids[i]];

        int64_t check = 0;
        for (size_t i = 0; i < N; i++) check += amt[i];

        auto report = [&](const char* m, double ms, size_t bytes, int64_t total) {
            printf("%-10zu %-22s %10.1f %10.2f %12.1f%s\n", G, m, ms, ms * 1e6 / N, bytes / 1e6,
                   total == check ? "" : "  WRONG");
        };

        {
            size_t before = heap_in_use();
            std::unordered_map<std::string, int64_t> m;
            double ms = time_ms([&] { for (size_t i = 0; i < N; i++) m[*skeys[i]] += amt[i]; });
            size_t bytes = heap_in_use() - before;
            int64_t t = 0; for (auto& [k, v] : m) t += v;
            report("unordered_map<string>", ms, bytes, t);
        }
        {
            size_t before = heap_in_use();
            std::unordered_map<uint32_t, int64_t> m;
            double ms = time_ms([&] { for (size_t i = 0; i < N; i++) m[ids[i]] += amt[i]; });
            size_t bytes = heap_in_use() - before;
            int64_t t = 0; for (auto& [k, v] : m) t += v;
            report("unordered_map<u32>", ms, bytes, t);
        }
        {
            size_t before = heap_in_use();
            FlatMap m(G);
            double ms = time_ms([&] { for (size_t i = 0; i < N; i++) m.add(ids[i], amt[i]); });
            size_t bytes = heap_in_use() - before;
            int64_t t = 0; for (auto v : m.vals) t += v;
            report("flat open-addressing", ms, bytes, t);
        }
        {
            size_t before = heap_in_use();
            std::vector<int64_t> sums(G);
            double ms = time_ms([&] { for (size_t i = 0; i < N; i++) sums[ids[i]] += amt[i]; });
            size_t bytes = heap_in_use() - before;
            int64_t t = 0; for (auto v : sums) t += v;
            report("array[id]", ms, bytes, t);
        }
        {
            // The one-time cost of getting dense ids: hash each string once at ingest.
            std::unordered_map<std::string, uint32_t> dict;
            std::vector<uint32_t> enc(N);
            double ms = time_ms([&] {
                for (size_t i = 0; i < N; i++) {
                    auto [it, _] = dict.try_emplace(*skeys[i], (uint32_t)dict.size());
                    enc[i] = it->second;
                }
            });
            printf("%-10zu %-22s %10.1f %10.2f %12s\n", G, "(dictionary encode)", ms, ms * 1e6 / N, "-");
        }
        puts("");
    }
}
