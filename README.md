# FBReader_Translator
For translating FBReader app strings
2025

## Why?

Since all the strings are split into multiple xml files with really deep folder structure, this repo tries to merge them into a single xml file for translation. It also records the original folder structure and tries to re-generate the structure for dispatching.

It might not be necessary to re-create the original folder structure since `'if your tool exports all the strings into a single XML file, that is perfectly fine.`, which has been stated on the [website](https://fbreader.org/translations). However, it may reduce the developer's time and speed up the releasing process anyway.

## How?

1. get `en.zip` as the reference data
2. unzip `en.zip` and flatten all strings into a single xml (e.g. `zh.xml`), a separate map file will be generated at the same time to record the entry-folder relationships (e.g. `mapping`)
3. translate the new generated `zh.xml`
4. re-create the folder structures for desired language according to `mapping` and `en.zip` (e.g. `zh` folder)
5. repack the translation folder (e.g. `zh`) as a zip file (e.g. `zh.zip`)
6. send the translated zip file (e.g. `zh.zip`) to developer for the next release

