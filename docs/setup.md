---
title: Setup
---

# Setup

## Before you start

### In Wildbook

- **An organization service key** (it starts with `wbsvc_`). Your
  organization's admin or a Wildbook admin creates it in Wildbook under
  **API Access → Organization service keys**. It keeps working until the expiry
  date Wildbook shows for it, so note that date and ask for a new key before
  then.
- The key's account must be able to see the sightings you want to bring
  across. A Wildbook admin account sees everything. A regular account only sees
  the records it has access to.
- The sightings must carry the `er=` label in their remarks. See
  [The label on each sighting](good-to-know.md#the-label-on-each-sighting).

!!! tip "Short-lived tokens also work, for testing"
    A token from **API Access → Read data** works too, but it expires after a
    few hours and the updates stop until someone pastes a new one. Use the
    service key for anything that should keep running.

### In EarthRanger

- **An event type with a list of animals.** Each event has a list field (for
  example *Animals* or *Herd*) with one row per animal, and inside each row the
  fields you want filled in: ID, sex, age, notes and photo, in any combination.
- **The field IDs.** For the list and for each field inside it, you need the
  ID as written in the event type's form, not the label people see. For example
  the label might be *Giraffe ID* while the ID is `giraffe_id`. Your EarthRanger
  admin can find these in the event type's settings.
- **Dropdown choices that match Wildbook.** If Sex or Age is a dropdown, its
  choices need to match Wildbook's values. See
  [How values are matched](good-to-know.md#how-values-are-matched).
- **A Photo field must be an attachment field**, if you want photos.
- **An EarthRanger user for Gundi** that can view and edit events of those
  types. Its token goes in the EarthRanger destination in Gundi (next section).

### In Gundi

- **An EarthRanger destination** for each site to update, with its address and
  token. If the site already sends or receives data through Gundi, it probably
  has one.
- Permission to create connections in your organization in the Gundi portal.

## Set up the connection

1. In the Gundi portal, add a new connection and choose **Wildbook** as the
   provider.
2. Add your EarthRanger destination (or several) to the connection.
3. Fill in the **Authentication** settings and click **Test Wildbook
   Connection**.
4. Fill in the **Update EarthRanger Events** settings and turn on **Run on
   schedule**.
5. After the next run (up to 20 minutes), open the connection's activity log to
   see the first report.

## Settings

### Authentication

| Setting | What to enter |
|---|---|
| **Wildbook Address** | Your Wildbook's web address as you open it in the browser, for example `https://giraffespotter.org`. |
| **API Token** | The organization service key (`wbsvc_…`), or a short-lived Read data token. |

### Update EarthRanger Events

| Setting | What to enter |
|---|---|
| **Run on schedule** | On, so it checks Wildbook every 20 minutes. |
| **List Field** | The ID of the list that holds one row per animal, for example `Herd`. Required. |
| **ID Field** | The ID of the field in each row that takes the animal's Wildbook name, for example `giraffe_id`. |
| **Sex Field** | The ID of the field that takes the animal's sex, for example `giraffe_sex`. |
| **Age Field** | The ID of the field that takes the animal's life stage, for example `giraffe_age`. |
| **Notes Field** | The ID of a text field that gets the Wildbook remarks added to it, for example `giraffe_notes`. |
| **Photo Field** | The ID of an attachment field that gets one photo of the animal, for example `giraffe_photo`. |
| **Photo Viewpoint** | Only use photos from this side, as Wildbook names it (for example `right`). Leave empty to take the first photo of any side. |
| **Start From** | Bring across Wildbook changes made on or after this date. Leave empty to start from the first run. See [Start date](good-to-know.md#start-date). |
| **Test Only: Copies Of Site** | Leave empty. It's only for test sites that hold copies of another site's events. |

Fill in at least one of ID, Sex, Age, Notes or Photo. Leave the others empty to
not touch them.

## Check it's working

The connection's **activity log** in the Gundi portal shows one entry per site
per run, for example:

- *twiga: 12 row(s) updated, 3 photo(s) added, 1 sighting(s) skipped*. The
  entry's details list each change (event, row, field, before and after) and
  why each skipped sighting was skipped.
- *twiga: no new Wildbook sightings for this site, nothing to update*. The run
  worked and there was nothing new.

An entry with skipped sightings shows as a warning, so it stands out.
