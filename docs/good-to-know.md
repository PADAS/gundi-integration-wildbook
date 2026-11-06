---
title: Good to know
---

# Good to know

## The label on each sighting

Gundi finds the EarthRanger row for a Wildbook sighting from a label in the
sighting's remarks:

```
er=<site>:<event number>:<row>
```

- **Site** is the first part of the EarthRanger address: `twiga` for
  `https://twiga.pamdas.org`. It must match the address of the destination in
  Gundi exactly.
- **Event number** is the number EarthRanger shows on the event, such as
  `#50325`.
- **Row** counts from 1: the third animal in the list is row 3.

The label can sit alongside other remarks, separated by `;` or `|`, for example
`UNIDENTIFIED; er=twiga:50325:3`.

Gundi only looks at sightings labelled for the site it's updating; sightings
without a label are never touched. A label it can't read is listed as skipped
in the activity log.

## Wildbook is the source for these fields

- Each time a sighting changes in Wildbook, Gundi writes its current values
  into the row, even if someone changed that row in EarthRanger in the
  meantime. Wildbook is treated as the reference for the fields you choose.
- If someone edits those fields in EarthRanger later, the edit stays until that
  sighting changes in Wildbook again.
- If someone edits the event in EarthRanger while Gundi is updating it, Gundi
  doesn't save over their edit. It tries again on the next run.

## Only changes are brought across

Gundi looks for sightings that **changed in Wildbook** since its last run. A
sighting whose animal isn't identified yet is skipped. When the animal is
identified later, that counts as a change, and the next run fills in the row.

## Start date

- With **Start From** empty, the first run only marks the starting point, and
  only Wildbook changes from then on are brought across.
- To bring across older sightings, set **Start From** before the first run.
- Start From only counts for the first run. After that, each run continues
  from where the last one stopped, so changing the date later has no effect.

## How values are matched

**ID**

- A text field gets the Wildbook name as it is, for example `HNBF093`.
- A dropdown gets the choice with that name. A choice that starts with the name
  followed by a nickname also counts, so `HNBF093` picks `HNBF093_Aubrey`.
- If two choices could fit, or none does, the field is left as it is.

**Sex and Age**

These are matched to the dropdown's choices, ignoring capitals, spaces,
hyphens and underscores, and accepting common short forms:

| Wildbook | Matches choices such as |
|---|---|
| male / female / unknown | Male, M / Female, F / Unknown, U |
| adult | Adult, Ad |
| subadult | Subadult, Sub-adult, SA |
| juvenile | Juvenile, Juv, Ju |
| calf | Calf, Ca |

- If the form has no Juvenile choice, a juvenile in Wildbook goes in as
  **Subadult**.
- If nothing fits, the field is left as it is, and the activity log notes the
  Wildbook value that had no choice. Adding that choice to the form fixes it
  for the next change.

**Notes**

- The Wildbook remarks are added after the notes already in the row, without
  the `er=` label and without the location note added on upload.
- They're added once. If the row already contains them, nothing changes.
- The Notes field must be a text field. A dropdown is left alone.

**Photo**

- Gundi adds one photo, only when the row's Photo field is empty.
- With **Photo Viewpoint** set, only photos whose viewpoint in Wildbook
  includes that word are used (`right` also matches `frontright`). If the
  animal has none, the row gets no photo.

## Sightings that are skipped

Each skipped sighting is listed in the activity log with its reason:

| Reason in the log | What it means |
|---|---|
| the stamp can't be read | The remarks have no `er=` label in the expected form. |
| the stamp is for another site | The label points to a different EarthRanger site. |
| the animal isn't identified in Wildbook yet | It will be picked up once the animal is matched. |
| event #… not found | No single event with that number on the site. |
| event #… has no row … | The event's list has fewer rows than the label says. |
| another sighting is stamped for event #… row … | Two sightings point to the same row, so only the first is used. |
| event type … has none of the fields | That event's type doesn't have the list or the fields set up in Gundi. |
| the event was edited in EarthRanger while updating it | It's tried again on the next run. |

## Animals in the background of a photo

Wildbook sometimes finds a second animal in the background of a photo and
creates an extra sighting for it with the same label. Extra sightings with no
sex and no life stage that share a label with another sighting are ignored, so
they don't overwrite the row of the animal that was actually reported.

## Several sites

- One Wildbook connection can update several EarthRanger sites. Add each one
  as a destination.
- Each site only receives sightings labelled with its own name, and keeps its
  own progress.
- All sites use the same field settings, so their event types need the same
  field IDs.

## Keys and tokens

- If the Wildbook key expires or is removed, updates stop and the activity log
  shows an error. Ask for a new key and paste it into the Authentication
  settings. The next run continues from where it stopped, so nothing is
  skipped.
- If the EarthRanger token in the destination stops working, updates to that
  site stop in the same way until it's replaced.
