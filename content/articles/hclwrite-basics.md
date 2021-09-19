---
title: "Generate fail HCL menggunakan library hclwrite"
date: 2021-09-19T12:25:34+08:00
---

HCL adalah bahasa yang digunakan dalam produk-produk daripada Hashicorp seperti Terraform dan Packer. Kebiasaannya, fail HCL ini ditulis secara manual tetapi jika anda ingin menulis atau mengubah fail-fail tersebut secara programmatik menggunakan code, maka anda boleh menggunakan [`hclwrite`](https://pkg.go.dev/github.com/hashicorp/hcl/v2@v2.10.1/hclwrite#Tokens), sebuah library yang ditulis dalam Go.

Blog post ini dibahagikan kepada dua bahagian. Bahagian pertama menunjukkan cara untuk menghasilkan block baru from scratch dan simpan ke fail. Ini adalah asas untuk bahagian kedua di mana kita akan mengubah fail HCL sedia ada dan memastikan format fail tersebut terjaga dan tidak melakukan pengubahan secara semberono.

Saya tidak akan memberi penerangan penuh syntax fail HCL kerana ia boleh didapati di [halaman ini](https://www.terraform.io/docs/language/syntax/configuration.html).


## Bahagian 1: Cipta block baru daripada mula

Untuk bahagian 1 ini, kita akan belajar cara untuk:

- cipta block baru
- tambah attribute dalam block tersebut
- simpan block yang dicipta ke dalam fail

Untuk contoh pertama, kita akan cuba generate block HCL di bawah:

```hcl
resource "github_membership" "user" {
  username = "github_username"
  role     = "member"
}
```

Inilah code yang diperlukan untuk generate block tersebut:

```go
newMemberBlock := hclwrite.NewBlock("resource", []string{"github_membership", mlId})
body := newMemberBlock.Body()
body.SetAttributeValue("username", cty.StringVal(githubUsername))
body.SetAttributeValue("role", cty.StringVal("members"))

f := hclwrite.NewEmptyFile()
f.Body().AppendBlock(newMemberBlock)
f.Body().AppendNewline()
ioutil.WriteFile("data/result_members.tf", hclwrite.Format(f.Bytes()), 0644)
```

### Cipta block

Mula-mula kita perlukan sebuah block untuk mengisi content-content lain ke dalamnya. Ini boleh dicipta menggunakan function `hclwrite.NewBlock()`. Parameter pertama function ini adalah nama type, kemudian diikuti dengan label-label bagi block tersebut. Dalam contoh block di atas, nama type yang kita perlukan adalah "resource" dan kita memerlukan label "github_membership" dan "user".

Seterusnya kita boleh mula mengisi boleh yang baru sahaja kita cipta tadi. Dalam contoh di atas, block itu mengandungi attribute "username" dan "role" dengan nilai masing-masing. Kita boleh set attribute sesebuah block dengan function `SetAttributeValue()`.

Untuk nama attribute, kita boleh menggunakan string biasa tetapi bagi nilai attribute tersebut, hclwrite menggunakan library `cty` (sebut: si-tai) untuk memastikan nilai attribute tersebut mempunyai type yang betul setelah habis proces pemprosesan nanti. Bagi memasukkan nilai string menggunakan library cty, kita boleh menggunakan function `cty.StringVal()`, yang akan menukarkan string Go biasa kepada nilai cty yang setaraf.

### Simpan block ke dalam fail

```go
f := hclwrite.NewEmptyFile()
f.Body().AppendBlock(newMemberBlock)
f.Body().AppendNewline()
ioutil.WriteFile("data/result_members.tf", hclwrite.Format(f.Bytes()), 0644)
```

Dengan itu selesai bahagian pertama iaitu mencipta block tersebut menggunakan code. Seterusnya, kita perlu menyimpan block yang telah kita cipta ini ke dalam fail. Untuk memudahkan, kali ini kita akan bermula dengan fail baru yang kosong. Untuk bermula dengan fail kosong, kita boleh menggunakan function `hclwrite.NewEmptyFile()`. Fuction ini seolah-olah memberi kita kanvas kosong untuk kita isikan dengan block-block yang akan kita reka.

Untuk menambah block ke fail tersebut, kita tidak boleh menambahnya terus ke objek `File` yang dipulangkan oleh function NewEmptyFile. Semua content dalam sebuah fail perlu diletakkan dalam bahagian `Body` block tersebut. Kita boleh mengakses Body melalui function `Body()`.

Seterusnya, kita boleh tambah block yang telah kita siapkan dalam bahagian sebelum ini menggunakan function `ApppendBlock` ke dalam Body yang telah dapat dalam langkah sebelum ini. Untuk memastikan block kita itu nampak kemas, maka kita boleh tambah baris kosong di hujung fail dengan menggunakan function `AppendNewLine`.

Akhirnya, untuk menyimpan semua yang telah kita generate ini ke fail, kita boleh menggunakan function `ioutil.WriteFile()`. Kita boleh memasukkan content fail kita dengan cara menukarkannya kepada `bytes`. hclwrite juga mempunyai function `Format` untuk memastikan fail yang telah kita cipta itu mematuhi recommended format untuk sesebuah fail HCL. Selepas itu anda bolehlah menyemak fail HCL yang dihasilkan di lokasi yang telah diberi semasa memanggil function `WriteFile` tadi.

## Bahagian 2: Mengubah block sedia ada

Untuk bahagian 2 ini, kita akan belajar cara untuk:

- baca dan parse fail HCL sedia ada
- cari bahagian untuk kita ubah
- tambah pengubahan yang diinginkan menggunakan Token
- beza `Traversal` dan `Value`

Fail yang ingin kita hasilkan adalah seperti berikut:

```hcl
module "team_itsm_team" {
  source = "../../modules/github/team_nx"

  team_name = "ITSM Team"

  members = [
    github_membership.kasan.username,
    github_membership.mismail.username, // *kita ingin menambah baris ini
  ]
}
```

```go
content, _ := ioutil.ReadFile("data/" + pod + ".tf")
f, _ := hclwrite.ParseConfig(content, "", hcl.InitialPos)

block := f.Body().FirstMatchingBlock("module", []string{"team_" + pod + "_team"})

oldMembers := block.Body().GetAttribute("members").Expr().BuildTokens(nil)
newEntry := hclwrite.NewExpressionAbsTraversal(
    hcl.Traversal{
        hcl.TraverseRoot{Name: "github_membership"},
        hcl.TraverseAttr{Name: mlId},
        hcl.TraverseAttr{Name: "username"},
    },
).BuildTokens(nil)

newMembers := append(
    oldMembers[:len(oldMembers)-2],
    &hclwrite.Token{Type: hclsyntax.TokenNewline, Bytes: []byte{'\n'}},
)
newMembers = append(newMembers, newEntry...)
newMembers = append(newMembers, hclwrite.Tokens{
    &hclwrite.Token{Type: hclsyntax.TokenComma, Bytes: []byte{','}},
    &hclwrite.Token{Type: hclsyntax.TokenNewline, Bytes: []byte{'\n'}},
    &hclwrite.Token{Type: hclsyntax.TokenCBrack, Bytes: []byte{']'}},
}...)

block.Body().SetAttributeRaw("members", newMembers)
ioutil.WriteFile("data/result_itsm.tf", hclwrite.Format(f.Bytes()), 0644)
```

### Baca dan parse fail HCL sedia ada

Kali ini kita tidak akan bermula dengan fail kosong, sebaliknya mengambil fail HCL yang sedia ada.

```go
content, _ := ioutil.ReadFile("data/" + pod + ".tf")
f, _ := hclwrite.ParseConfig(content, "", hcl.InitialPos)
```

Kita menggunakan function `ReadFile` untuk membaca keseluruhan fail tersebut. Function tersebut akan memulangkan content dalam bentuk `[]byte` yang akan kita berikan kepada function `hclwrite.ParseConfig()`. Function inilah yang bertanggungjawab memahami syntax sedia ada fail HCL tersebut dan membolehkan kita mengubah fail itu dengan tepat. Function ini akan memulangkan objeck `hclwrite.File`, sama seperti function `hclwrite.NewEmptyFile()` di bahagian 1.

### Cari bahagian untuk kita ubah

Terdapat pelbagai cara yang boleh kita gunakan untuk mencari bahagian tertentu yang ingin kita ubah. Antaranya ialah dengan menggunakan function `FirstMatchingBlock()`.
Kita perlu menetapkan jenis (type) block yang ingin dicari, kemudian diikuti dengan label-label yang ada pada block tersebut.

```go
block := f.Body().FirstMatchingBlock("module", []string{"team_" + pod + "_team"})
```

### Tambah pengubahan yang diinginkan

```go
oldMembers := block.Body().GetAttribute("members").Expr().BuildTokens(nil)
newEntry := hclwrite.NewExpressionAbsTraversal(
    hcl.Traversal{
        hcl.TraverseRoot{Name: "github_membership"},
        hcl.TraverseAttr{Name: mlId},
        hcl.TraverseAttr{Name: "username"},
    },
).BuildTokens(nil)

newMembers := append(
    oldMembers[:len(oldMembers)-2],
    &hclwrite.Token{Type: hclsyntax.TokenNewline, Bytes: []byte{'\n'}},
)
newMembers = append(newMembers, newEntry...)
newMembers = append(newMembers, hclwrite.Tokens{
    &hclwrite.Token{Type: hclsyntax.TokenComma, Bytes: []byte{','}},
    &hclwrite.Token{Type: hclsyntax.TokenNewline, Bytes: []byte{'\n'}},
    &hclwrite.Token{Type: hclsyntax.TokenCBrack, Bytes: []byte{']'}},
}...)

block.Body().SetAttributeRaw("members", newMembers)
```

Dapatkan nilai attribute yang ingin kita ubah melalui function `GetAttribute()`. Nilai attribute ini merupakan sebuah expression. Untuk mengubahnya kita perlu menukarkannya kepada `Token`.

#### Apa itu Token?

TODO

#### Beza Traversal dan literal Value

Traversal digunakan untuk merujuk kepada variable lain dalam fail HCL tersebut. Literal value tidak merujuk kepada mana-mana bahagian lain dalam fail/projek, berdiri dengan sendiri.

### Simpan fail yang diubah

```go
ioutil.WriteFile("data/result_itsm.tf", hclwrite.Format(f.Bytes()), 0644)
```

## Konklusi

Manipulasi fail HCL menggunakan library hclwrite lebih kompleks daripada melakukan ubahsuai secara manual tetapi jika ini perkara yang anda perlu lakukan setiap hari, mungkin lebih senang jika anda meluangkan masa beberapa hari untuk membangunkan solusi automation ini supaya perkara yang sama tidak perlu lagi intervensi manual daripada anda.


### Sumber Rujukan

- [Terraform Configuration Syntax](https://www.terraform.io/docs/language/syntax/configuration.html)
- [hclwrite package documentation](https://pkg.go.dev/github.com/hashicorp/hcl/v2@v2.10.1/hclwrite)
- [Write Terraform Files in Go with hclwrite](https://dev.to/pdcommunity/write-terraform-files-in-go-with-hclwrite-2e1j)
