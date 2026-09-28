#include <malloc/malloc.h>
#include <cstdio>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>
static size_t inuse(){ malloc_statistics_t s; malloc_zone_statistics(nullptr,&s); return s.size_in_use; }
int main(){
  for (size_t G : {1000000ul, 10000000ul}) {
    size_t b = inuse(); { std::vector<int64_t> v(G); printf("%zu array %.1f MB\n", G, (inuse()-b)/1e6); }
    b = inuse(); { std::unordered_map<uint32_t,int64_t> m; for (uint32_t i=0;i<G;i++) m[i*2654435761u]+=1; printf("%zu umap<u32> %.1f MB buckets=%zu\n", G, (inuse()-b)/1e6, m.bucket_count()); }
    b = inuse(); { std::unordered_map<std::string,int64_t> m; for (size_t i=0;i<G;i++) m["user_"+std::to_string(1000000000ull+i)]+=1; printf("%zu umap<string> %.1f MB sizeof(string)=%zu\n", G, (inuse()-b)/1e6, sizeof(std::string)); }
  }
}
