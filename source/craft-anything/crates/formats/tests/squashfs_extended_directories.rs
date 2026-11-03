use craft_anything_formats::fsread::{self, Limits};
use craft_anything_testkit::firmware::{squashfs_image, squashfs_image_with_extended_directories};

fn check_directories(root: bool, nested: bool) {
    let limits = Limits::default();
    let expected = fsread::read("squashfs", &squashfs_image(), &limits).unwrap();
    assert!(expected.complete);
    assert_eq!(expected.entries.len(), 3);
    let bytes = squashfs_image_with_extended_directories(root, nested);
    let actual = fsread::read("squashfs", &bytes, &limits).unwrap();
    // Compare the names, kinds, contents and completeness, not only the number of entries.
    assert_eq!(actual, expected);
}

#[test]
fn reads_an_extended_root_directory() {
    check_directories(true, false);
}

#[test]
fn reads_an_extended_nested_directory_at_a_nonzero_offset() {
    check_directories(false, true);
}

#[test]
fn reads_extended_root_and_nested_directories_together() {
    check_directories(true, true);
}
