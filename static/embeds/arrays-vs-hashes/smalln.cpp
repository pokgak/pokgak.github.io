// Point lookups in a small map: linear scan of a flat array vs hash tables.
// This is why Redis stores small hashes as a listpack instead of a hash table.
// clang++ -O2 -std=c++20 -march=native smalln.cpp -o smalln
#include <algorithm>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <random>
#include <string>
#include <unordered_map>
#include <vector>

using Clock = std::chrono::steady_clock;

int main() {
    const size_t Q = 20'000'000;
    std::mt19937_64 rng(7);
    printf("%-6s %-24s %8s\n", "n", "method", "ns/op");
    for (size_t n : {4, 8, 16, 32, 64, 128, 256, 1024}) {
        std::vector<std::string> fields(n);
        for (size_t i = 0; i < n; i++) fields[i] = "field_" + std::to_string(i * 7919);
        std::vector<uint32_t> ikeys(n);
        for (size_t i = 0; i < n; i++) ikeys[i] = (uint32_t)(i * 2654435761u);

        std::vector<std::pair<std::string, int64_t>> sarr;
        std::unordered_map<std::string, int64_t> smap;
        std::vector<std::pair<uint32_t, int64_t>> iarr;
        std::unordered_map<uint32_t, int64_t> imap;
        for (size_t i = 0; i < n; i++) {
            sarr.push_back({fields[i], (int64_t)i});
            smap[fields[i]] = i;
            iarr.push_back({ikeys[i], (int64_t)i});
            imap[ikeys[i]] = i;
        }
        std::vector<uint32_t> qi(Q);
        for (auto& q : qi) q = rng() % n;

        auto run = [&](const char* name, auto&& f) {
            int64_t sink = 0;
            auto t0 = Clock::now();
            for (size_t i = 0; i < Q; i++) sink += f(qi[i]);
            double ns = std::chrono::duration<double, std::nano>(Clock::now() - t0).count() / Q;
            printf("%-6zu %-24s %8.2f   (%lld)\n", n, name, ns, (long long)sink % 10);
        };

        run("scan array<string>", [&](uint32_t q) {
            const std::string& k = fields[q];
            for (auto& [f, v] : sarr) if (f == k) return v;
            return (int64_t)-1;
        });
        run("unordered_map<string>", [&](uint32_t q) { return smap.find(fields[q])->second; });
        run("scan array<u32>", [&](uint32_t q) {
            uint32_t k = ikeys[q];
            for (auto& [f, v] : iarr) if (f == k) return v;
            return (int64_t)-1;
        });
        run("unordered_map<u32>", [&](uint32_t q) { return imap.find(ikeys[q])->second; });
        puts("");
    }
}
