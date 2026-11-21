export function sanitizeForTTS(text: string): string {
    if (!text) return "";
    let s = text.trim();

    // 0. Remove visual source attributions and parentheticals from speech (keep concise and natural)
    s = s.replace(/\b(?:according to (?:wikipedia|official records|reports|sources?)|as per (?:wikipedia|sources?))\s*[,:]?\s*/gi, "");
    s = s.replace(/\(source:[^)]+\)/gi, "");
    s = s.replace(/\(result \d+\)/gi, "");

    // 1. Remove Markdown code blocks & inline code
    s = s.replace(/```[\s\S]*?```/g, "");
    s = s.replace(/`([^`]+)`/g, "$1");

    // 2. Snake_case into separate words FIRST (so _case_ is not mistaken for italics)
    s = s.replace(/(?<=\w)_(?=\w)/g, " ");

    // 3. Remove Markdown bold and italics
    s = s.replace(/\*\*(.*?)\*\*/g, "$1");
    s = s.replace(/\*(.*?)\*/g, "$1");
    s = s.replace(/__(.*?)__/g, "$1");
    s = s.replace(/_(.*?)_/g, "$1");

    // 4. Remove Markdown headers
    s = s.replace(/^#+\s*/gm, "");

    // 5. Bullet lists and numbered lists -> turn into sentences with periods
    s = s.replace(/^\s*[\*\-\+]\s+(.*)$/gm, "$1. ");
    s = s.replace(/^\s*\d+\.\s+(.*)$/gm, "$1. ");

    // 6. Colons: preserve time formats like 10:30 AM
    s = s.replace(/(?<=\d):(?=\d{2}\b)/g, "___TIME_COLON___");
    // Convert all other colons into a natural pause (comma + space)
    s = s.replace(/:\s*/g, ", ");
    s = s.replace(/___TIME_COLON___/g, ":");

    // 7. Semicolons into natural pauses
    s = s.replace(/;\s*/g, ", ");

    // 8. Strip remaining unwanted symbols
    s = s.replace(/[*~`#><|^\\{}[\]()]/g, "");

    // 9. Clean up multiple punctuation and whitespace
    s = s.replace(/,\s*,+/g, ",");
    s = s.replace(/\s+([,.\?!])/g, "$1");
    s = s.replace(/\s+/g, " ").trim();
    s = s.replace(/^[\s,]+/, "");

    // 10. Check if any alphanumeric character exists; return empty if none
    if (!/[a-zA-Z0-9]/.test(s)) {
        return "";
    }

    return s;
}

export function splitIntoSpokenSentences(text: string): string[] {
    const cleaned = sanitizeForTTS(text);
    if (!cleaned) return [];

    // Abbreviation-aware sentence splitting:
    // Protect:
    // 1. Person initials like "C. Joseph", "J. K. Rowling", "A. P. J."
    // 2. Decimals like "3.14", "99.9"
    // 3. Common abbreviations like "Dr.", "Mr.", "Mrs.", "Prof.", "vs.", "e.g.", "i.e.", "etc."
    let protectedText = cleaned;

    // Protect initials (single uppercase letter followed by dot): e.g. "C." -> "C___DOT___"
    protectedText = protectedText.replace(/\b([A-Z])\.(?=\s+[A-Za-z])/g, "$1___DOT___");

    // Protect decimals (digit dot digit): e.g. "3.14" -> "3___DOT___14"
    protectedText = protectedText.replace(/(\d+)\.(\d+)/g, "$1___DOT___$2");

    // Protect common abbreviations
    const abbrevs = ["dr", "mr", "mrs", "ms", "prof", "vs", "eg", "e\\.g", "ie", "i\\.e", "etc", "jr", "sr", "st", "inc", "ltd", "co"];
    for (const abb of abbrevs) {
        const regex = new RegExp(`\\b(${abb})\\.(?=\\s+)`, "gi");
        protectedText = protectedText.replace(regex, "$1___DOT___");
    }

    // Split on sentence-ending punctuation (. ? !)
    const rawSentences = protectedText.split(/(?<=[.?!])\s+/);
    const validSentences: string[] = [];

    for (const sent of rawSentences) {
        const restored = sent.replace(/___DOT___/g, ".").trim();
        if (!/[a-zA-Z0-9]/.test(restored)) continue;

        // Also allow splitting on (, ; :) when a clause is sufficiently long (~25 characters)
        if (restored.length > 50 && /[,;:]\s+/.test(restored)) {
            const clauses = restored.split(/(?<=[,;:])\s+/);
            let currentClause = "";
            for (const cl of clauses) {
                if (currentClause.length >= 25) {
                    if (/[a-zA-Z0-9]/.test(currentClause)) validSentences.push(currentClause.trim());
                    currentClause = cl;
                } else {
                    currentClause = currentClause ? `${currentClause} ${cl}` : cl;
                }
            }
            if (currentClause && /[a-zA-Z0-9]/.test(currentClause)) {
                validSentences.push(currentClause.trim());
            }
        } else {
            validSentences.push(restored);
        }
    }

    return validSentences;
}
