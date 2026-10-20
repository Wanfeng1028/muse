# Packaging for upload

Write `videos/<slug>/youtube.md` for the user. Never upload or post anything yourself.

- **Title:** 3 options. For explainers, "X Explained in N Minutes (and <the angle>)" works; N is
  the real runtime rounded up. Under 60 characters before the brackets.
- **Description:** first two lines say what the viewer gets (they show in search). Then
  `chapters.txt` (written by the build; YouTube needs the first one at 0:00 and at least three),
  then the sources from `brief.md`, then 3 to 5 hashtags.
- **Captions:** upload `captions.srt` (written by the build) instead of relying on auto-captions.
- **Thumbnail:** 1280x720. 2 to 4 huge words, one accent colour, one picture from the video,
  readable at 168px wide. Check it at that size next to the competing thumbnails, not full size.
- **Pinned comment:** one question that invites an answer about the viewer's own use case.
