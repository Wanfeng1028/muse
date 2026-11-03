use craft_anything_formats::bun_program::BunProgram;
use craft_anything_formats::packed::PackedFormat;
use craft_anything_testkit::packed::{BunModule, bun_appended, bun_graph, bun_module};

#[test]
fn reports_stored_text_encodings_without_transcoding_bytes() {
    let text = "café 🍵\n";
    let wide: Vec<u8> = text.encode_utf16().flat_map(u16::to_le_bytes).collect();
    let modules = [
        BunModule { encoding: 2, loader: 13, format: 0, ..bun_module("/$bunfs/root/wide.txt", &wide) },
        BunModule { encoding: 1, loader: 13, format: 0, ..bun_module("/$bunfs/root/latin.txt", b"caf\xe9") },
        BunModule { encoding: 0, loader: 5, format: 0, ..bun_module("/$bunfs/root/raw.bin", b"\x00\xff\x80") },
    ];
    for record_bytes in [36, 52] {
        for offsets_bytes in [24, 32] {
            let bytes = bun_appended(&bun_graph(&modules, 0, "", record_bytes, offsets_bytes));
            let listing = BunProgram.list(&bytes).unwrap();
            assert_eq!(listing.entries.len(), 3);
            for (entry, (encoding, expected)) in listing.entries.iter().zip([("utf16le", wide.as_slice()), ("latin1", b"caf\xe9"), ("binary", b"\x00\xff\x80")])
            {
                assert!(entry.kind.as_deref().unwrap().split_whitespace().any(|part| part == format!("encoding={encoding}")), "{:?}", entry.kind);
                assert_eq!(BunProgram.read(&bytes, entry, 1024).unwrap(), expected);
            }
            let raw = BunProgram.read(&bytes, &listing.entries[0], 1024).unwrap();
            assert!(std::str::from_utf8(&raw).is_err());
            let (pairs, remainder) = raw.as_chunks::<2>();
            assert!(remainder.is_empty());
            let units: Vec<u16> = pairs.iter().copied().map(u16::from_le_bytes).collect();
            assert_eq!(String::from_utf16(&units).unwrap(), text);
        }
    }
}
