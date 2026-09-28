// Same array[id] aggregation, 10M groups: random row order vs rows clustered by id.
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <random>
#include <vector>
int main() {
    const size_t N = 20'000'000, G = 10'000'000;
    std::mt19937_64 rng(42);
    std::vector<uint32_t> ids(N);
    for (auto& x : ids) x = rng() % G;
    auto run = [&](const char* name) {
        std::vector<int64_t> sums(G);
        auto t0 = std::chrono::steady_clock::now();
        for (size_t i = 0; i < N; i++) sums[ids[i]] += i & 1023;
        double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
        int64_t t = 0; for (auto v : sums) t += v;
        printf("%-12s %8.1f ms %6.2f ns/row (%lld)\n", name, ms, ms * 1e6 / N, (long long)t % 7);
    };
    run("random");
    std::sort(ids.begin(), ids.end());
    run("sorted");
}
