import re
from PyQt6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextDocument
from PyQt6.QtCore import Qt
import os  # For factory function

# --- State Constants for Multi-line Constructs ---
STATE_DEFAULT = 0
STATE_MULTILINE_COMMENT = 1  # Generic multi-line comment (/* C */, <!-- HTML/XML -->)
STATE_TRIPLE_QUOTE_STRING = 2 # Python triple-quoted string (non-docstring)
STATE_DOCSTRING = 3           # Python docstring
STATE_TEMPLATE_LITERAL = 4    # JavaScript template literal ``
# No state needed for f-string interpolation, handled within string rule application
# STATE_FSTRING_INTERP = 5 # Deprecated - handled internally

# States for embedded contexts (Must be distinct from above)
STATE_EMBEDDED_JS_IN_HTML = 10
STATE_EMBEDDED_CSS_IN_HTML = 11
# XML Specific state
STATE_XML_CDATA = 12          # <<< NEW State for XML CDATA


class SyntaxHighlighter(QSyntaxHighlighter):
    """
    Enhanced base class for syntax highlighters with multi-line support,
    robust embedding, and improved rule application logic.
    """
    def __init__(self, document: QTextDocument | None, colors: dict):
        if not isinstance(document, QTextDocument):
            # In scenarios where a highlighter might be created temporarily
            # without a document (e.g., for caching), allow None but issue warning.
            # Production use typically requires a valid document immediately.
             if document is not None:
                  print("Warning: Invalid document passed to SyntaxHighlighter. Expecting QTextDocument.")
             # Allow proceeding without document for potential setup/caching cases,
             # but it won't function until setDocument is called properly.
             super().__init__(document) # Pass parent arg if it's meant to be document's parent
        else:
             super().__init__(document)

        # Basic check for colors dict
        self.colors = colors if isinstance(colors, dict) else {}
        if not self.colors:
            print("Warning: Invalid or empty colors dictionary passed to SyntaxHighlighter. Using fallback.")
            # Provide basic fallback colors (essential for operation)
            self.colors = {
                "black": "#1e222a", "white": "#abb2bf", "gray2": "#2e323a",
                "gray3": "#545862", "gray4": "#6d8dad", "blue": "#61afef",
                "green": "#7EC7A2", "red": "#e06c75", "orange": "#caaa6a",
                "yellow": "#EBCB8B", "pink": "#c678dd"
                }

        # --- Expanded Formats ---
        # Helper to safely create format with fallback color
        def _create_format_safe(color_key: str, fallback: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
             color_hex = self.colors.get(color_key, fallback)
             fmt = QTextCharFormat()
             try:
                 qcolor = QColor(color_hex)
                 if not qcolor.isValid():
                     raise ValueError(f"Invalid color hex: {color_hex}")
                 fmt.setForeground(qcolor)
                 if bold: fmt.setFontWeight(QFont.Weight.Bold)
                 if italic: fmt.setFontItalic(True)
             except Exception as e:
                 print(f"Warning: Failed to create format for '{color_key}' (color={color_hex}). Using fallback '{fallback}'. Error: {e}")
                 try:
                    # Attempt to set fallback color even on error
                    fallback_color = QColor(fallback)
                    if fallback_color.isValid():
                        fmt.setForeground(fallback_color)
                    # Ignore bold/italic on error
                 except Exception as fe:
                    print(f"Error: Fallback color '{fallback}' also invalid: {fe}")
                    # Last resort: default Qt color (usually black)
                    pass
             return fmt

        # Common formats across languages
        self.formats = {
            'keyword': _create_format_safe('blue', '#61afef'),
            'keyword_decl': _create_format_safe('blue', '#61afef', bold=True), # class, def, function, const
            'keyword_ctrl': _create_format_safe('pink', '#c678dd'),           # return, if, for, while, etc.
            'keyword_imp': _create_format_safe('pink', '#c678dd'),            # import, export, from, <?target in XML?
            'builtin': _create_format_safe('red', '#e06c75'),                # print, len, Math, console
            'special_var': _create_format_safe('yellow', '#EBCB8B'),          # self, this, True, False, null
            'operator': _create_format_safe('white', '#abb2bf'),              # +, -, *, =, ==, =>
            'brace': _create_format_safe('white', '#abb2bf'),                 # (), {}, []
            'punctuation': _create_format_safe('white', '#abb2bf'),           # ,, ;, :
            'number': _create_format_safe('red', '#e06c75'),
            'func_name': _create_format_safe('green', '#7EC7A2'),
            'class_name': _create_format_safe('orange', '#caaa6a', bold=True),
            'decorator': _create_format_safe('pink', '#c678dd', bold=True),   # @decorator
            'string': _create_format_safe('green', '#98C379'),                # Base string content
            'string_escape': _create_format_safe('pink', '#c678dd', bold=True),# \n, \t, \\
            'string_special': _create_format_safe('yellow', '#EBCB8B', italic=True),# f/r prefix, {}/ ${} interp. markers, <![CDATA[ delimiters
            'docstring': _create_format_safe('gray4', '#6d8dad', italic=True),# Python docstring """..."""
            'regex': _create_format_safe('pink', '#c678dd'),                 # /regex/ or r'...'? Context matters.
            'comment': _create_format_safe('gray4', '#6d8dad', italic=True), # //, #, /*...*/, <!-- ... -->, <!DOCTYPE...>
            # HTML/XML Specific
            'html_tag': _create_format_safe('blue', '#61afef'),           # <tag>, </tag>, <>, <? ?>, <! ]]>, name
            'html_attr_name': _create_format_safe('yellow', '#EBCB8B'),     # attribute=
            'html_attr_value': _create_format_safe('green', '#98C379'),    # "value"
            'html_entity': _create_format_safe('red', '#e06c75'),         # &
            # CSS Specific
            'css_selector': _create_format_safe('pink', '#c678dd'),        # .class, #id, tag
            'css_property': _create_format_safe('white', '#abb2bf'),        # color:
            'css_value': _create_format_safe('green', '#98C379'),          # blue, 12px, inherit
            # JSON Specific
            'json_key': _create_format_safe('blue', '#61afef'),           # "key":
        }

        self.single_line_rules = []
        self.multiline_triggers = {} # Stores definitions for multi-line constructs

        # Cache for sub-highlighters (one instance per type needed)
        # Key: The factory function (e.g., JavaScriptHighlighter)
        # Value: The highlighter instance
        self._sub_highlighters_cache = {}


    def _get_sub_highlighter(self, factory):
        """Gets or creates a cached sub-highlighter instance."""
        if factory not in self._sub_highlighters_cache:
            try:
                # Create with current colors, but NO document (it operates on segments)
                instance = factory(None, self.colors)
                # We need to assign setFormat capability from the parent
                # instance.setFormat = self.setFormat # DANGEROUS: Breaks if context changes!
                # Safer: Sub-highlighter needs a reference to the parent/main highlighter
                # Or pass the parent's setFormat method explicitly during call?
                # Simpler for now: assume it inherits setFormat by being a QSyntaxHighlighter
                self._sub_highlighters_cache[factory] = instance
                print(f"Debug: Cached sub-highlighter instance for {factory.__name__}")
            except Exception as e:
                print(f"Error: Failed to create sub-highlighter {factory.__name__}: {e}")
                return None
        instance = self._sub_highlighters_cache.get(factory)
        if instance and not hasattr(instance, 'highlight_segment'):
             print(f"Warning: Sub-highlighter {factory.__name__} is missing 'highlight_segment' method.")
             # return None # Optionally disable if method is missing
        return instance

    # --- Main Highlighting Logic ---
    def highlightBlock(self, text: str):
        if not hasattr(self, 'formats') or not self.formats:
             # Initialization likely failed or colours were bad
             # Avoid processing if formats aren't ready.
             # print("Debug: Skipping highlightBlock - formats not ready.")
             return

        applied_range = [False] * len(text)
        start_offset = 0
        current_state = self.previousBlockState()
        if current_state == -1: current_state = STATE_DEFAULT

        # --- 1. Handle continuation of multi-line states / embedded highlighting ---

        # Check if we are in an embedded state or special multiline state (CDATA)
        sub_highlighter_factory = None
        current_trigger = None
        for trigger_key, trigger_info in self.multiline_triggers.items():
            if trigger_info['state'] == current_state:
                current_trigger = trigger_info
                sub_info = trigger_info.get('sub_highlighter')
                if sub_info:
                    sub_highlighter_factory = sub_info['factory']
                break # Found the trigger matching the current state

        if current_trigger:
            end_pattern = current_trigger.get('end')
            sub_highlighter = self._get_sub_highlighter(sub_highlighter_factory) if sub_highlighter_factory else None
            end_match = end_pattern.search(text, 0) if end_pattern else None

            if end_match:
                # Multi-line or Embedded block ENDS on this line
                content_len_or_delim_start = end_match.start()
                end_delimiter_len = end_match.end() - end_match.start()

                # A. Highlight content using sub-highlighter (if embedded)
                if sub_highlighter:
                    content_len = content_len_or_delim_start
                    if content_len > 0:
                        try: sub_highlighter.highlight_segment(self, text, 0, content_len)
                        except Exception as e: print(f"Error during sub-highlighting segment (end): {e}")
                    for i in range(content_len): applied_range[i] = True # Mark sub-highlighted range

                # B. Apply base internal format for non-embedded multiline content (up to end delim)
                elif current_trigger.get('internal_format') and current_trigger['internal_format'] in self.formats:
                     content_len = content_len_or_delim_start
                     if content_len > 0:
                          try: self.setFormat(0, content_len, self.formats[current_trigger['internal_format']])
                          except Exception as e: print(f"Error applying internal fmt (end): {e}")
                     for i in range(content_len): applied_range[i] = True # Mark content range

                # C. Apply special rules WITHIN the content if needed (before formatting end delim)
                # If not embedded, maybe apply_rules_within_range needed? e.g., for complex comments
                content_len = content_len_or_delim_start
                self.apply_rules_within_range(text, 0, content_len, current_state)

                # Format the closing delimiter
                fmt_key = current_trigger.get('format_key')
                if fmt_key and fmt_key in self.formats and end_delimiter_len > 0:
                    self.setFormat(end_match.start(), end_delimiter_len, self.formats[fmt_key])
                for i in range(end_match.start(), end_match.end()): applied_range[i] = True # Mark delimiter range

                # Reset state and set offset for the rest of the line
                self.setCurrentBlockState(STATE_DEFAULT)
                start_offset = end_match.end()
                current_state = STATE_DEFAULT # Update local state too

            else:
                # Multi-line or Embedded block CONTINUES past this line
                content_len = len(text)
                state_to_keep = current_trigger['state']

                # A. Highlight using sub-highlighter (if embedded)
                if sub_highlighter:
                    if content_len > 0:
                         try: sub_highlighter.highlight_segment(self, text, 0, content_len)
                         except Exception as e: print(f"Error during sub-highlighting segment (cont): {e}")

                # B. Apply base internal format for non-embedded multiline content (entire line)
                elif current_trigger.get('internal_format') and current_trigger['internal_format'] in self.formats:
                     if content_len > 0:
                          try: self.setFormat(0, content_len, self.formats[current_trigger['internal_format']])
                          except Exception as e: print(f"Error applying internal fmt (cont): {e}")
                
                # C. Apply special rules WITHIN the content (whole line)
                self.apply_rules_within_range(text, 0, content_len, current_state)


                # Keep the state and mark whole line applied
                self.setCurrentBlockState(state_to_keep)
                for i in range(len(text)): applied_range[i] = True
                return # Entire block consumed

        elif current_state != STATE_DEFAULT:
            # Previous state exists but doesn't match any known multiline trigger
            # This could happen if a state definition was removed or invalid. Reset safely.
            print(f"Warning: Unhandled continuation state {current_state}. Resetting to DEFAULT.")
            self.setCurrentBlockState(STATE_DEFAULT)
            current_state = STATE_DEFAULT


        # If we reach here, we are either starting fresh (STATE_DEFAULT) or processing
        # the remainder of a line after a multi-line/embedded block ended. `start_offset` is set.

        # --- 2. Find all potential single/multi-line START matches from start_offset ---
        if start_offset < len(text): # Only search if there's text left
             # Only search for NEW starts if we are in DEFAULT state
             # (Embed/multiline continuations already handled above)
             matches = self._find_matches(text, current_state, start_offset) if current_state == STATE_DEFAULT else []
             # Sort: start pos (asc), length (desc - longer matches first), rule index (asc - stability)
             matches.sort(key=lambda m: (m['match'].start(), -(m['match'].end() - m['match'].start()), m['rule_index']))
        else:
             matches = [] # No text left to process

        # --- 3. Apply formats, resolving overlaps ---
        last_applied_end = start_offset
        did_set_state_in_loop = False # Track if state was set by a *new* multi-line block

        for match_info in matches:
            match = match_info['match']
            match_start = match.start()
            match_end = match.end()

            # Skip if match starts before the current processing point or is fully covered
            if match_start < start_offset or match_start < last_applied_end: continue
            # Check if the start of the match is already formatted (overlap)
            # Use careful check: apply if *any part* is unformatted initially
            is_already_covered = True
            if match_start >= match_end: continue # Skip zero-length or invalid
            for k in range(match_start, min(match_end, len(applied_range))):
                if k >= 0 and k < len(applied_range) and not applied_range[k]:
                    is_already_covered = False
                    break
            if is_already_covered: continue

            # Safety check for match end
            match_end = min(match_end, len(text))
            if match_start >= match_end: continue

            if match_info['type'] == 'single':
                was_applied = self._apply_single_line_match(match_info, text, applied_range)
                if was_applied:
                    # Update last_applied_end based on the actual range marked in applied_range
                    new_end = match_start
                    for k in range(match_start, len(applied_range)):
                        if k < len(applied_range) and applied_range[k]: new_end = k + 1
                        else:
                           # Don't necessarily break; allow gaps and continue checking
                           # Only advance if contiguous block from start was applied
                           if k == match_start: break # Nothing applied at start? Stop.
                           pass
                    # More reliable update: find max applied index within the overall match span
                    max_idx_in_match = -1
                    for k in range(match_start): # Use original match end
                         if k < len(applied_range) and applied_range[k]:
                             max_idx_in_match = k
                    if max_idx_in_match >= match_start: # Something was applied
                        last_applied_end = max(last_applied_end, max_idx_in_match + 1)
                    # else: maybe nothing applied due to sub-rules overlap logic

            elif match_info['type'] == 'multi_start':
                trigger_key = match_info['trigger_key']
                trigger = self.multiline_triggers[trigger_key]
                sub_highlighter_info = trigger.get('sub_highlighter')

                # Apply the initial part of the multiline/embedded block STARTING at match_start
                # `apply_multiline_format` handles start delim format, content format (if basic), and state setting
                consumed_length, ended_on_line = self.apply_multiline_format(text, match_start, trigger, trigger_key, is_continuation=False)
                actual_end = min(match_start + consumed_length, len(text))

                # Mark the range covered by this START segment (delimiters + potential initial content)
                for k in range(match_start, actual_end):
                    if k < len(applied_range): applied_range[k] = True

                last_applied_end = max(last_applied_end, actual_end)
                # state is set by apply_multiline_format based on ended_on_line

                # Calculate start delimiter length for content processing below
                start_delim_len = 0
                start_match_re = trigger['start'].match(text, match_start)
                if start_match_re:
                    start_delim_len = start_match_re.end() - start_match_re.start()
                else:
                     print(f"Warning: Multiline start trigger '{trigger_key}' match inconsistency.")
                     # Handle error? Perhaps assume zero length delimiter for safety
                     # start_delim_len = 0


                content_start_here = match_start + start_delim_len
                content_len_here = actual_end - content_start_here

                # If EMBEDDED highlight, apply SUB-HIGHLIGHTER to the content on THIS line (after start delim)
                if sub_highlighter_info and content_len_here > 0:
                    sub_factory = sub_highlighter_info['factory']
                    sub_hl = self._get_sub_highlighter(sub_factory)
                    if sub_hl:
                        try:
                            sub_hl.highlight_segment(self, text, content_start_here, content_len_here)
                        except Exception as e: print(f"Error during sub-highlighting segment (start): {e}")

                # If REGULAR multiline, apply INTERNAL RULES (e.g. escapes, but *not* handled by base apply_multiline_format)
                elif not sub_highlighter_info and content_len_here > 0:
                      # Determine the extent of the content before potential end delimiter on same line
                      true_internal_len = content_len_here
                      if ended_on_line and trigger.get('end'):
                           end_match_inline = trigger['end'].search(text, content_start_here)
                           if end_match_inline and end_match_inline.start() >= content_start_here:
                               true_internal_len = end_match_inline.start() - content_start_here
                           # else: End delimiter found elsewhere or not at all, use consumed len based calc

                      if true_internal_len > 0:
                           self.apply_rules_within_range(text, content_start_here, true_internal_len, trigger['state'])

                if not ended_on_line:
                    # This multi-line block continues, processing STOPS here for this line.
                    did_set_state_in_loop = True # Mark that state was set
                    # Ensure rest of line isn't processed by subsequent matches in *this* block
                    last_applied_end = len(text) # Consume rest of line conceptually
                    for k in range(actual_end, len(text)): # Mark rest applied too, preventing single line rule hits
                        if k < len(applied_range): applied_range[k] = True
                    break # Stop processing further matches on this line

                # else: ended on line, state was reset to DEFAULT by apply_multiline_format, loop continues

        # --- 4. Final State Handling ---
        # State is managed primarily by apply_multiline_format or embedding logic.
        # If we started in default state and no multiline/embed block took over, ensure state remains default.
        # If we started in a non-default state, the continuation logic should have either kept it or reset it.
        if self.currentBlockState() == -1:
             # If state somehow remained uninitialized (e.g., errors, empty line), default it.
             self.setCurrentBlockState(STATE_DEFAULT)


    def _find_matches(self, text: str, current_state: int, start_offset: int) -> list:
        """Finds single-line and multiline START triggers from start_offset."""
        matches = []
        # Only apply rules/find triggers if in default state (continuations handled elsewhere)
        if current_state == STATE_DEFAULT:
            # Add single-line rules
            for rule_index, rule_info in enumerate(self.single_line_rules):
                # Add validation for rule_info format
                if not isinstance(rule_info, (tuple, list)) or not rule_info:
                     # print(f"Warning: Skipping invalid rule definition at index {rule_index}.")
                     continue
                if isinstance(rule_info, tuple) and len(rule_info) >= 1 and isinstance(rule_info[0], re.Pattern):
                     pattern = rule_info[0]
                     fmt_info = rule_info[1] if len(rule_info) > 1 else None # Assume group 0 if no format key? Bad idea. Requires key.
                     if not fmt_info:
                          # print(f"Warning: Single line rule at index {rule_index} is missing format info.")
                          continue
                else:
                     # Allow lists like [[pattern1, fmt1], [pattern2, fmt2]]? No, design is [(pattern, fmt),...]
                     # print(f"Warning: Malformed single line rule at index {rule_index}.")
                     continue

                try:
                    for match in pattern.finditer(text, start_offset):
                        matches.append({
                            'match': match, 'format_info': fmt_info,
                            'type': 'single', 'rule_index': rule_index # Rule index for stable sort
                        })
                except re.error as e: print(f"Warning: Regex error in single_line_rules[{rule_index}] ('{pattern.pattern}'): {e}")
                except Exception as e: print(f"Warning: Error processing single_line_rules[{rule_index}]: {e}")

            # Add multiline start triggers
            trigger_keys = list(self.multiline_triggers.keys())
            for key_index, key in enumerate(trigger_keys):
                trigger = self.multiline_triggers.get(key)
                if not trigger or 'start' not in trigger or 'state' not in trigger:
                     print(f"Warning: Invalid multiline trigger definition for key '{key}'.")
                     continue
                
                pattern = trigger['start']
                if not isinstance(pattern, re.Pattern):
                     print(f"Warning: Invalid 'start' pattern for multiline trigger '{key}'.")
                     continue

                # Rule index offset: Start after single lines, use key order for stability + priority
                base_idx = len(self.single_line_rules)
                priority_boost = trigger.get('priority', 0)
                rule_index_effective = max(0, base_idx + key_index - priority_boost * 10) # Adjust calculation if needed

                try:
                    for match in pattern.finditer(text, start_offset):
                        matches.append({
                           'match': match, 'trigger_key': key,
                           'type': 'multi_start', 'rule_index': rule_index_effective
                        })
                except re.error as e: print(f"Warning: Regex error in multiline_triggers['{key}']['start'] ('{pattern.pattern}'): {e}")
                except Exception as e: print(f"Warning: Error processing multiline trigger '{key}': {e}")

        return matches


    def _apply_single_line_match(self, match_info: dict, text: str, applied_range: list[bool]) -> bool:
        """
        Applies formats for a single-line rule match, respecting applied_range for overlaps.
        Handles multiple capture groups within one rule definition using list format.
        Returns True if *any* part of the match was formatted, False otherwise.
        """
        match = match_info['match']
        fmt_info = match_info['format_info']
        rule_pattern = match.re # For debugging/context
        match_start_overall, match_end_overall = match.start(), match.end()
        applied_something = False

        # Standardize fmt_info to a list of tuples: [(format_key, group_index_or_name), ...]
        processed_fmt_list = []
        if isinstance(fmt_info, str): # Single format key for group 0 (whole match)
            processed_fmt_list = [(fmt_info, 0)]
        elif isinstance(fmt_info, tuple) and len(fmt_info) >= 2 and isinstance(fmt_info[0], str) and isinstance(fmt_info[1], (int, str)):
             # Single tuple (format_key, group)
             processed_fmt_list = [fmt_info]
        elif isinstance(fmt_info, list):
            # List of (key, group) tuples or simple list of keys (apply all to group 0)
            all_keys_for_group_0 = True
            for item in fmt_info:
                if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[0], str) and isinstance(item[1], (int, str)):
                    processed_fmt_list.append(item)
                    all_keys_for_group_0 = False
                elif isinstance(item, str) and all_keys_for_group_0:
                    # Only append string if we haven't seen tuples yet
                    processed_fmt_list.append((item, 0))
                elif isinstance(item, str):
                     # Mixed list - strings apply to group 0 by convention here
                     processed_fmt_list.append((item, 0))

        if not processed_fmt_list:
            # print(f"Debug: No valid formats for match: '{match.group(0)}' Rule: '{rule_pattern.pattern}'")
            return False

        # --- Iterate through each format/group specified by the rule ---
        # Sort by group start index? No, rule definition order should suffice mostly.
        for format_key, target_group in processed_fmt_list:
            if not format_key or format_key not in self.formats:
                # print(f"Debug: Format key '{format_key}' not found or invalid.")
                continue
            try:
                # Get the span of the specific capture group
                group_start, group_end = match.start(target_group), match.end(target_group)
            except IndexError:
                print(f"Warning: Invalid group '{target_group}' for rule '{rule_pattern.pattern}' match '{match.group(0) if match.re.groups > 0 else 'group 0'}'. Groups: {match.groups()}")
                continue
            # Handle non-participating group name? Raised ValueError before.
            except ValueError as e:
                 print(f"Warning: Invalid group name/ref '{target_group}' for rule '{rule_pattern.pattern}'. Error: {e}")
                 continue


            if group_start == -1 or group_end == -1: continue # Group didn't participate in match
            if group_end <= group_start: continue # Skip empty or invalid span

            # --- Apply format respecting applied_range for this group's span ---
            current_pos = group_start
            while current_pos < group_end:
                # Find the start of the next available segment within the group span
                while current_pos < group_end and (current_pos >= len(applied_range) or applied_range[current_pos]):
                    current_pos += 1

                # If no available position is left in the group span, break
                if current_pos >= group_end: break

                # Find the end of this contiguous available segment
                segment_start = current_pos
                segment_end = segment_start
                # Be careful with range check: segment_end goes up to group_end
                while segment_end < group_end and (segment_end < len(applied_range) and not applied_range[segment_end]):
                    segment_end += 1

                # Apply format to this segment
                apply_len = segment_end - segment_start
                if apply_len > 0:
                    try:
                        # Ensure range is valid for setFormat
                        if segment_start >= 0 and segment_start + apply_len <= len(text):
                            self.setFormat(segment_start, apply_len, self.formats[format_key])
                            # Mark this segment as applied
                            for k in range(segment_start, segment_end):
                                if k < len(applied_range): applied_range[k] = True
                            applied_something = True
                        else:
                             print(f"Warning: Invalid range calculation for formatting. Key='{format_key}', Start={segment_start}, Len={apply_len}, TextLen={len(text)}.")
                    except ValueError as ve: # Catch potential Qt errors on invalid range
                        print(f"Warning: Formatting ValueError (range likely invalid): Key='{format_key}', Start={segment_start}, Len={apply_len}, TextLen={len(text)}. Error: {ve}")
                        break # Avoid repeated errors on this span
                    except Exception as e:
                        print(f"Warning: Error applying format '{format_key}' at {segment_start} len {apply_len}: {e}")
                        break # Avoid repeated errors on this span

                # Move current_pos to the end of the segment just processed (or blocked)
                current_pos = segment_end

        return applied_something


    def apply_multiline_format(self, text: str, start_index: int, trigger: dict, trigger_key: str, is_continuation: bool) -> tuple[int, bool]:
        """
        Applies formatting for a multi-line construct (start or continuation).
        Handles delimiters using 'format_key'. Applies 'internal_format' to content.
        Sets the block state appropriately. Does NOT call apply_rules_within_range here.
        Returns: tuple (consumed_char_count_on_this_line, ended_on_this_line: bool).
        """
        main_format_key = trigger.get('format_key') # For delimiters
        # Use internal_format for content; if None, content isn't formatted by default here.
        content_format_key = trigger.get('internal_format')
        end_pattern = trigger.get('end')
        next_state = trigger['state'] # State to set *if continuing*

        main_fmt = self.formats.get(main_format_key) if main_format_key else None
        content_fmt = self.formats.get(content_format_key) if content_format_key else None

        consumed_len = 0
        search_for_end_from = start_index # Default for continuation

        # --- Format Start Delimiter (if not a continuation) ---
        start_match_len = 0
        if not is_continuation:
            start_pattern = trigger['start']
            start_match = start_pattern.match(text, start_index)
            if start_match:
                start_match_len = start_match.end() - start_match.start()
                search_for_end_from = start_match.end() # Search for end *after* start delim
                if main_fmt and start_match_len > 0:
                    try:
                        self.setFormat(start_match.start(), start_match_len, main_fmt)
                    except Exception as e: print(f"Error formatting multiline start: {e}")
                consumed_len += start_match_len
            else:
                 # This is unexpected if triggered by finditer, suggests logic issue.
                 print(f"Warning: Multiline trigger '{trigger_key}' start pattern mismatch at {start_index}. Text:'{text[start_index:start_index+10]}...' Pattern: '{trigger['start'].pattern}'")
                 # Safely assume it didn't start correctly, reset state.
                 self.setCurrentBlockState(STATE_DEFAULT)
                 return 0, True # Treat as ended immediately

        # --- Find End Delimiter ---
        end_match = None
        if end_pattern:
            try:
                # Search only from where the content starts
                end_match = end_pattern.search(text, search_for_end_from)
            except re.error as e: print(f"Warning: Regex error in multiline end pattern for '{trigger_key}' ('{end_pattern.pattern}'): {e}")
            except Exception as e: print(f"Warning: General error searching for multiline end: {e}")

        # --- Apply Formatting to Content and End Delimiter ---
        if not end_match: # Continues to next line
            content_start = search_for_end_from
            content_len = len(text) - content_start # Content is rest of line
            if content_len > 0 and content_fmt:
                 try: self.setFormat(content_start, content_len, content_fmt)
                 except Exception as e: print(f"Error formatting multiline content (cont): {e}")
            # Only add content length if formatted, consumed_len should track actual formatted/delimited part
            consumed_len += content_len # Consumes the whole line conceptually
            self.setCurrentBlockState(next_state) # Set state for continuation
            return consumed_len, False # Did NOT end on line

        else: # Ends on this line
            content_start = search_for_end_from
            content_len = end_match.start() - content_start # Content is between delimiters
            if content_len > 0 and content_fmt:
                 try: self.setFormat(content_start, content_len, content_fmt)
                 except Exception as e: print(f"Error formatting multiline content (end): {e}")
            consumed_len += content_len # Add content length to consumption

            # Format the end delimiter
            end_match_len = end_match.end() - end_match.start()
            if end_match_len > 0:
                if main_fmt:
                    try: self.setFormat(end_match.start(), end_match_len, main_fmt)
                    except Exception as e: print(f"Error formatting multiline end: {e}")
                consumed_len += end_match_len # Add delimiter length to consumption

            self.setCurrentBlockState(STATE_DEFAULT) # End state is Default
            return consumed_len, True # Did end on line

    # --- Hooks for Subclasses ---

    def apply_rules_within_range(self, text: str, start: int, length: int, current_multiline_state: int, **kwargs):
        """
        Placeholder/Hook for applying SUB-rules within a delimited region
        that has already received a base format (e.g., escapes in strings,
        interpolation markers in f-strings/template literals). Called AFTER
        base content/delimiter formatting.

        Args:
            text (str): The full text of the current block.
            start (int): Start index of the segment within the block's text.
            length (int): Length of the segment.
            current_multiline_state (int): The state active for this segment
                                           (e.g., STATE_TRIPLE_QUOTE_STRING).
            **kwargs: Optional extra context (e.g., is_fstring=True).
        """
        # Base implementation does nothing. Subclasses override this.
        pass

    def highlight_segment(self, parent_highlighter: QSyntaxHighlighter, text_segment: str, block_start_offset: int):
        """
        Method called by a PARENT highlighter to apply THIS highlighter's rules
        to a specific segment of text within the parent's context (EMBEDDING).
        Relies on parent_highlighter.setFormat().

        Args:
            parent_highlighter (QSyntaxHighlighter): The main highlighter instance.
            text_segment (str): The piece of text to highlight.
            block_start_offset (int): Starting index within the ORIGINAL text block.
        """
        if not hasattr(parent_highlighter, 'setFormat') or not callable(parent_highlighter.setFormat):
             print(f"Error ({self.__class__.__name__}): highlight_segment called without valid parent_highlighter.")
             return

        segment_len = len(text_segment)
        segment_applied_range = [False] * segment_len # Local applied range

        # --- Find Matches within Segment ---
        # Note: This simple version uses _find_matches restricted to STATE_DEFAULT
        # which only finds single-line rules and *new* multiline starts within the segment.
        # It does NOT handle multiline constructs continuing *into* or *out of* the segment robustly.
        seg_matches = self._find_matches(text_segment, STATE_DEFAULT, 0)
        seg_matches.sort(key=lambda m: (m['match'].start(), -(m['match'].end() - m['match'].start()), m['rule_index']))

        # --- Apply Matches using parent's setFormat ---
        seg_last_applied_end = 0
        for match_info in seg_matches:
             match = match_info['match']
             seg_match_start, seg_match_end = match.start(), match.end()

             if seg_match_start < seg_last_applied_end: continue
             # Check overlap within segment range
             is_seg_already_covered = True
             if seg_match_start >= seg_match_end: continue
             for k in range(seg_match_start, min(seg_match_end, segment_len)):
                 if k >= 0 and k < segment_len and not segment_applied_range[k]:
                     is_seg_already_covered = False
                     break
             if is_seg_already_covered: continue

             fmt_info = match_info['format_info']
             # Simplified logic from _apply_single_line_match, using parent.setFormat
             processed_fmt_list = []
             # (Code repeated for standardizing fmt_info - potential helper function?)
             if isinstance(fmt_info, str): processed_fmt_list = [(fmt_info, 0)]
             elif isinstance(fmt_info, tuple): processed_fmt_list = [fmt_info]
             elif isinstance(fmt_info, list):
                 for item in fmt_info:
                     if isinstance(item, str): processed_fmt_list.append((item, 0))
                     elif isinstance(item, tuple): processed_fmt_list.append(item)

             for format_key, target_group in processed_fmt_list:
                 if not format_key or format_key not in self.formats: continue
                 try:
                     group_start_seg, group_end_seg = match.start(target_group), match.end(target_group)
                 except IndexError: continue
                 except ValueError: continue # Added for invalid name safety
                 
                 if group_start_seg == -1 or group_end_seg == -1 or group_end_seg <= group_start_seg: continue

                 # --- Apply format to non-applied parts within the segment group span ---
                 current_seg_pos = group_start_seg
                 while current_seg_pos < group_end_seg:
                     while current_seg_pos < group_end_seg and (current_seg_pos >= segment_len or segment_applied_range[current_seg_pos]):
                          current_seg_pos += 1
                     if current_seg_pos >= group_end_seg: break

                     sub_segment_start_seg = current_seg_pos
                     sub_segment_end_seg = sub_segment_start_seg
                     while sub_segment_end_seg < group_end_seg and (sub_segment_end_seg < segment_len and not segment_applied_range[sub_segment_end_seg]):
                          sub_segment_end_seg += 1

                     apply_abs_start = block_start_offset + sub_segment_start_seg
                     apply_abs_len = sub_segment_end_seg - sub_segment_start_seg

                     if apply_abs_len > 0:
                         try:
                             # Use the PARENT's setFormat with absolute positions
                             parent_highlighter.setFormat(apply_abs_start, apply_abs_len, self.formats[format_key])
                             # Mark applied range within the SEGMENT
                             for k in range(sub_segment_start_seg, sub_segment_end_seg):
                                 if k < segment_len: segment_applied_range[k] = True
                         except Exception as e:
                             print(f"Error in highlight_segment parent.setFormat: {e} at {apply_abs_start}, len {apply_abs_len}")
                             break # Avoid repeated errors

                     current_seg_pos = sub_segment_end_seg # Move position

             # Update last applied end within segment
             max_applied_in_match = -1
             for k in range(seg_match_start, seg_match_end):
                 if k < segment_len and segment_applied_range[k]:
                      max_applied_in_match = k
             if max_applied_in_match >= seg_match_start:
                 seg_last_applied_end = max(seg_last_applied_end, max_applied_in_match + 1)


# ======================================================
# --- Python Highlighter ---
# ======================================================
class PythonHighlighter(SyntaxHighlighter):
    """Syntax highlighter for Python with multi-line, docstrings, and f-string support."""
    def __init__(self, document: QTextDocument | None, colors: dict):
        super().__init__(document, colors)

        keywords_decl = ['class', 'def']
        keywords_ctrl = ['return', 'yield', 'continue', 'break', 'pass', 'raise', 'assert', 'del', 'global', 'nonlocal']
        keywords_imp = ['import', 'from', 'as']
        keywords_other = ['and', 'await', 'async', 'elif', 'else', 'except', 'finally', 'for', 'if', 'in', 'is', 'lambda', 'not', 'or', 'try', 'while', 'with', 'match', 'case'] # Added match/case
        booleans_consts = ['True', 'False', 'None']
        builtins_list = [ # Common builtins
            'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'breakpoint', 'bytearray', 'bytes', 'callable', 'chr',
            'classmethod', 'compile', 'complex', 'delattr', 'dict', 'dir', 'divmod', 'enumerate',
            'eval', 'exec', 'filter', 'float', 'format', 'frozenset', 'getattr', 'globals',
            'hasattr', 'hash', 'help', 'hex', 'id', 'input', 'int', 'isinstance', 'issubclass',
            'iter', 'len', 'list', 'locals', 'map', 'max', 'memoryview', 'min', 'next', 'object',
            'oct', 'open', 'ord', 'pow', 'print', 'property', 'range', 'repr', 'reversed',
            'round', 'set', 'setattr', 'slice', 'sorted', 'staticmethod', 'str', 'sum', 'super',
            'tuple', 'type', 'vars', 'zip', '__import__']
        special_vars = ['self', 'cls']

        # Pre-compile Regexes (using raw strings)
        self.RULE_COMMENT = re.compile(r'#[^\n]*')
        self.RULE_DECORATOR = re.compile(r'@([\w\.]+)')
        # Basic type hints (less aggressive matching) - might style generics poorly
        # Avoid lookbehind: match : \s* type or -> \s* type
        self.RULE_TYPEHINT = re.compile(r'(?:[:]\s*|->\s*)(\b[a-zA-Z_][\w\.]*(?:\[.+?\])?\b)') # Match type name after : or ->
        self.RULE_BRACKETS_TYPES = re.compile(r'[\[\]]') # Only brackets []

        self.RULE_DEF = re.compile(r'\b(def)\s+([a-zA-Z_]\w*)\b')
        self.RULE_CLASS = re.compile(r'\b(class)\s+([a-zA-Z_]\w*)\b')
        # Keywords (bound strictly)
        kw_pattern = lambda words: r'\b(?:' + '|'.join(words) + r')\b'
        self.RULE_KW_DECL = re.compile(kw_pattern(keywords_decl))
        self.RULE_KW_CTRL = re.compile(kw_pattern(keywords_ctrl))
        self.RULE_KW_IMP = re.compile(kw_pattern(keywords_imp))
        self.RULE_KW_OTHER = re.compile(kw_pattern(keywords_other))
        self.RULE_CONSTS = re.compile(kw_pattern(booleans_consts))
        # Match builtins conservatively (avoid obj.builtin_name)
        self.RULE_BUILTINS = re.compile(r'(?<!\.)' + kw_pattern(builtins_list))
        self.RULE_SPECIAL_VARS = re.compile(kw_pattern(special_vars))
        # Numbers (Order: Hex/Oct/Bin -> Float -> Int)
        self.RULE_NUM_HEXOCTBIN = re.compile(r'\b(?:0[xX][0-9a-fA-F]+[lL]?|0[oO][0-7]+[lL]?|0[bB][01]+[lL]?)\b')
        self.RULE_NUM_FLOAT = re.compile(r'\b(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][-+]?[0-9]+)?[jJ]?\b')
        self.RULE_NUM_INT = re.compile(r'\b[0-9]+(?:[eE][-+]?[0-9]+)?[jJ]?(?!\.)\b') # Ensure not followed by '.' (part of float)
        self.RULE_OPERATOR = re.compile(r':=|->|[+\-*/%<>=!&|^~@.]|(?<!\w)not(?!\w)|(?<!\w)is(?!\w)|(?<!\w)in(?!\w)') # Added 'not', 'is', 'in' as ops
        self.RULE_BRACES_GENERAL = re.compile(r'[\(\)\{\}]') # Exclude [] handled separately
        self.RULE_PUNCTUATION = re.compile(r'[:,;]')

        # String Rules: Prefix handled by multiline triggers or _apply_single_line_match override
        self.RULE_SINGLE_QUOTE = re.compile(r"([urfURF]*)'([^'\\]*(?:\\.[^'\\]*)*)'")
        self.RULE_DOUBLE_QUOTE = re.compile(r'([urfURF]*)"([^"\\]*(?:\\.[^"\\]*)*)"')
        # String Escape and F-String Interpolation patterns (used in apply_rules_within_range)
        self.RULE_STR_ESCAPE_COMP = re.compile(r'\\.') # Simple general escape
        self.RULE_FSTR_INTERP_COMP = re.compile(r'(\{\{)|(\}\})|(\{([^\{\}]*?)\})') # {{, }}, or {expr}

        rules = [
            (self.RULE_COMMENT, 'comment'),
            (self.RULE_DECORATOR, [('decorator', 1)]), # Decorator name after @
            (self.RULE_TYPEHINT, [('builtin', 1)]),    # Type name (group 1)
            (self.RULE_DEF, [('keyword_decl', 1), ('func_name', 2)]),
            (self.RULE_CLASS, [('keyword_decl', 1), ('class_name', 2)]),
            # Keywords must be checked before potentially overlapping identifiers/builtins
            (self.RULE_KW_DECL, 'keyword_decl'),
            (self.RULE_KW_CTRL, 'keyword_ctrl'),
            (self.RULE_KW_IMP, 'keyword_imp'),
            (self.RULE_KW_OTHER, 'keyword'), # Includes 'not', 'is', 'in' - operator rule also catches them? Need priority check. Make operators lower prio.
            (self.RULE_CONSTS, 'special_var'),
            (self.RULE_BUILTINS, 'builtin'),
            (self.RULE_SPECIAL_VARS, 'special_var'),
            (self.RULE_NUM_HEXOCTBIN, 'number'),
            (self.RULE_NUM_FLOAT, 'number'),
            (self.RULE_NUM_INT, 'number'),
            (self.RULE_OPERATOR, 'operator'), # Lower priority than keywords
            (self.RULE_BRACES_GENERAL, 'brace'),
            (self.RULE_PUNCTUATION, 'punctuation'),
            (self.RULE_BRACKETS_TYPES, 'brace'), # Separate for potential different styling later
            # String rules (complex): Need special handling for prefix/content/internal
            # These rules define capture groups, _apply_single_line_match interprets them.
             # Prefix(1), Content(2)
            (self.RULE_SINGLE_QUOTE, [('string_special', 1), ('string', 2)]),
            (self.RULE_DOUBLE_QUOTE, [('string_special', 1), ('string', 2)]),
        ]
        self.single_line_rules = rules

        self.multiline_triggers = {
            # Docstrings (must be detected early in line) have higher priority
            'docstring': {
                 # Match """ or ''' potentially preceded by whitespace AT START OF LINE or after 'def/class...'
                 # Simple start-of-line match for performance, less accurate for indented ones after code.
                 'start': re.compile(r'^[ \t]*("""|\'\'\')'), # Start of line only version
                 #'start': re.compile(r'(?:(?<=^\s*)|(?<=\w\s*)|(?<=[):]\s*))("""|\'\'\')'), # Complex lookbehind attempt (fragile)
                 'end': re.compile(r'"""|\'\'\''),
                 'state': STATE_DOCSTRING, 'format_key': 'docstring', # Use special docstring format
                 'internal_format': 'docstring', # Content is also docstring styled
                 'priority': 20 # High priority
             },
            # Regular triple-quoted strings (can include prefixes)
            'string3': {
                 # Match prefix (group 1), then """ or ''' (group 2)
                 'start': re.compile(r'\b([urfURF]*)("""|\'\'\')'),
                 'end': re.compile(r'"""|\'\'\''),
                 'state': STATE_TRIPLE_QUOTE_STRING,
                 'format_key': 'string_special',        # Delimiters styled as special? or 'string'? Let's use 'string_special'
                 'internal_format': 'string',           # Content styled as string
                 'priority': 5                          # Lower priority than docstring
                 # Prefix group (1) needs special formatting done in override
             },
        }

    # Override to handle string prefixes and trigger internal formatting
    def _apply_single_line_match(self, match_info: dict, text: str, applied_range: list[bool]) -> bool:
        match = match_info['match']
        rule_pattern = match.re
        applied = False

        # Special handling for string rules to format prefix AND trigger internal rules
        if rule_pattern == self.RULE_SINGLE_QUOTE or rule_pattern == self.RULE_DOUBLE_QUOTE:
            prefix_group_idx = 1
            content_group_idx = 2

            # 1. Format Prefix (Group 1) if it exists
            prefix = match.group(prefix_group_idx) if match.re.groups >= prefix_group_idx else None
            prefix_applied = False
            if prefix:
                 prefix_applied = self._apply_format_to_group(match_info, prefix_group_idx, 'string_special', text, applied_range)
                 applied = applied or prefix_applied


            # 2. Format Content (Group 2) - base string format
            content_applied = False
            if match.re.groups >= content_group_idx:
                 content_applied = self._apply_format_to_group(match_info, content_group_idx, 'string', text, applied_range)
                 applied = applied or content_applied

            # 3. If content was formatted (at least partially), apply internal rules
            if content_applied:
                 content_start, content_end = match.start(content_group_idx), match.end(content_group_idx)
                 if content_start != -1 and content_end > content_start:
                     # Calculate the range within the content group that *was actually* formatted
                     # to avoid applying internal rules over blocked regions.
                     first_formatted = -1
                     last_formatted = -1
                     for k in range(content_start, content_end):
                         # Check within bounds of applied_range
                         if k < len(applied_range) and applied_range[k]:
                              # Only consider indices that *were just applied* by _apply_format_to_group above for 'string'
                              # Check if it maps back to this rule application? Complex state needed.
                              # Simplified: Assume if applied_range[k] is true *now*, it's okay to run internal rules over it.
                              if first_formatted == -1: first_formatted = k
                              last_formatted = k
                     
                     if first_formatted != -1:
                          internal_start = first_formatted
                          internal_len = (last_formatted - first_formatted) + 1

                          # Determine flags for internal rules
                          prefix_lower = prefix.lower() if prefix else ''
                          is_fstring = 'f' in prefix_lower
                          is_raw = 'r' in prefix_lower
                          # Apply escapes, f-string interpolation etc.
                          self.apply_rules_within_range(text, internal_start, internal_len, STATE_DEFAULT, is_fstring=is_fstring, is_raw=is_raw)

            return applied # Return whether anything was done for this rule

        # Handle start of triple-quoted string prefix (already handled by apply_multiline_format override)
        # This override should mainly focus on SINGLE LINE constructs.

        # Base class method handles the generic group application now,
        # let's ensure this Python one doesn't interfere unless necessary.
        # Python mainly needs internal rules applied.
        # Is the base _apply_single_line_match sufficient?
        # No, because it doesn't call apply_rules_within_range. So keep the override.
        else:
            # Use default implementation for all other non-string rules
            return super()._apply_single_line_match(match_info, text, applied_range)


    # Helper (could be moved to base class if universally useful)
    def _apply_format_to_group(self, match_info: dict, group_index: int | str, format_key: str, text: str, applied_range: list[bool]) -> bool:
        """Helper to apply format to a specific group, respecting overlap."""
        match = match_info['match']
        if format_key not in self.formats: return False

        try:
            group_start, group_end = match.start(group_index), match.end(group_index)
        except IndexError: return False
        except ValueError: return False # Handle invalid group name
        if group_start == -1 or group_end == -1: return False
        format_length = group_end - group_start
        if format_length <= 0: return False

        applied_group = False
        current_pos = group_start
        while current_pos < group_end:
            # Skip already applied positions
            while current_pos < group_end and (current_pos >= len(applied_range) or applied_range[current_pos]):
                current_pos += 1
            if current_pos >= group_end: break

            segment_start = current_pos
            segment_end = segment_start
            # Find end of contiguous non-applied segment within group span
            while segment_end < group_end and (segment_end < len(applied_range) and not applied_range[segment_end]):
                segment_end += 1

            apply_len = segment_end - segment_start
            if apply_len > 0:
                try:
                    # Check range validity
                    if segment_start >= 0 and segment_start + apply_len <= len(text):
                         self.setFormat(segment_start, apply_len, self.formats[format_key])
                         # Mark as applied
                         for k in range(segment_start, segment_end):
                             if k < len(applied_range): applied_range[k] = True
                         applied_group = True
                    else:
                        print(f"Warning (Python _apply_group): Invalid range. Start={segment_start}, Len={apply_len}, TextLen={len(text)}")

                except Exception as e:
                    print(f"Error in Python _apply_format_to_group: {e}")
                    break # Stop on error for this group
            current_pos = segment_end

        return applied_group

    # Override to handle prefix in triple-quotes and trigger internal rules
    def apply_multiline_format(self, text: str, start_index: int, trigger: dict, trigger_key: str, is_continuation: bool) -> tuple[int, bool]:
        """Overrides base to handle Python triple-quote prefixes and context for internal rules."""
        prefix_info = {'is_fstring': False, 'is_raw': False}
        start_delim_len_incl_prefix = 0 # Includes length of prefix + """/'''

        # 1. Handle prefix formatting ONLY when starting 'string3'
        if trigger_key == 'string3' and not is_continuation:
             start_pattern = trigger['start'] # \b([urfURF]*)("""|\'\'\')
             start_match = start_pattern.match(text, start_index)
             if start_match:
                  start_delim_len_incl_prefix = start_match.end() - start_match.start()
                  prefix = start_match.group(1).lower() if start_match.group(1) else ''
                  prefix_start, prefix_end = start_match.start(1), start_match.end(1)
                  prefix_len = prefix_end - prefix_start
                  if prefix_len > 0:
                       fmt = self.formats.get('string_special')
                       if fmt:
                            try: self.setFormat(prefix_start, prefix_len, fmt)
                            # Do NOT mark applied_range here, rely on highlightBlock overlap
                            except Exception as e: print(f"Error formatting triple quote prefix: {e}")
                  prefix_info['is_fstring'] = 'f' in prefix
                  prefix_info['is_raw'] = 'r' in prefix

                  # Also format the """/''' delimiter itself using the trigger's format_key
                  delim_start, delim_end = start_match.start(2), start_match.end(2)
                  delim_len = delim_end - delim_start
                  main_fmt = self.formats.get(trigger.get('format_key'))
                  if main_fmt and delim_len > 0:
                      try: self.setFormat(delim_start, delim_len, main_fmt)
                      except Exception as e: print(f"Error formatting triple quote delim: {e}")
             else:
                # This case shouldn't happen based on highlightBlock logic
                print(f"Warning (Python apply_multi): Start match failed for {trigger_key} at {start_index}")
                self.setCurrentBlockState(STATE_DEFAULT)
                return 0, True

        # 2. Call base implementation AFTER potential prefix/start delim formatting
        # The base handles finding end, applying *internal_format* to content, formatting end delim, and setting state.
        # Pass is_continuation along. Note that the base `setFormat` calls might override the prefix/start delim format if spans overlap; overlap logic in `highlightBlock` aims to prevent this later.
        # We are formatting prefix/delim *before* base class, base might reformat content over it if internal_format is set. This might be acceptable.
        # Base call also determines consumed length and ending status.
        # However, the base method *also* formats the start delimiter if !is_continuation. This is redundant.
        # Let's call a MODIFIED or separate path of the base logic?
        # Alternative: Let base handle start delim (main_fmt), then *re-apply* prefix fmt if needed? Seems messy.
        # --> Let's rethink: The base apply_multiline_format handles start/end delimiters (main_fmt) and content (content_fmt).
        # --> Python needs: Special prefix fmt, special delimiter fmt ('string_special'), content fmt ('string'), and internal rules.
        # --> Modify base slightly? Or handle entirely here?
        # --> Try handling string3 entirely here for more control:

        if trigger_key == 'string3':
            # --- Full handling for Python triple quotes ('string3') ---
            main_fmt_py = self.formats.get(trigger.get('format_key')) # Delimiters ('string_special')
            content_fmt_py = self.formats.get(trigger.get('internal_format')) # Content ('string')
            end_pattern_py = trigger.get('end')
            next_state_py = trigger['state']

            consumed_len_py = 0
            search_offset_py = start_index
            
            if not is_continuation:
                # Start delimiter formatting done above (prefix + delim)
                consumed_len_py += start_delim_len_incl_prefix # Add length of prefix+delimiter
                search_offset_py = start_index + start_delim_len_incl_prefix
            
            end_match_py = end_pattern_py.search(text, search_offset_py) if end_pattern_py else None

            ended_on_line_py = bool(end_match_py)

            content_start_py = search_offset_py
            content_end_py = end_match_py.start() if ended_on_line_py else len(text)
            content_len_py = content_end_py - content_start_py
            
            # Apply base content format
            if content_len_py > 0 and content_fmt_py:
                 try: self.setFormat(content_start_py, content_len_py, content_fmt_py)
                 except Exception as e: print(f"Error setting Python string3 content fmt: {e}")
            consumed_len_py += content_len_py

            # Apply internal rules (escapes, f-strings) over the content span
            if content_len_py > 0:
                 self.apply_rules_within_range(text, content_start_py, content_len_py, next_state_py, **prefix_info)

            # Handle end delimiter and state
            if ended_on_line_py:
                 end_delim_len_py = end_match_py.end() - end_match_py.start()
                 if end_delim_len_py > 0 and main_fmt_py:
                      try: self.setFormat(end_match_py.start(), end_delim_len_py, main_fmt_py)
                      except Exception as e: print(f"Error formatting Python string3 end delim: {e}")
                 consumed_len_py += end_delim_len_py
                 self.setCurrentBlockState(STATE_DEFAULT)
            else:
                 self.setCurrentBlockState(next_state_py)

            return consumed_len_py, ended_on_line_py

        elif trigger_key == 'docstring':
             # Use base implementation for docstrings (simpler, just one format)
             consumed_len, ended_on_line = super().apply_multiline_format(text, start_index, trigger, trigger_key, is_continuation)
             # Docstrings generally don't need complex internal rules like escapes/f-strings
             # Could add simple escape rule application here if desired via apply_rules_within_range
             return consumed_len, ended_on_line

        else:
             # Should not happen for Python if only docstring/string3 defined
             return super().apply_multiline_format(text, start_index, trigger, trigger_key, is_continuation)

    def apply_rules_within_range(self, text: str, start: int, length: int, current_state: int, **kwargs):
        """Highlight escapes and f-string interpolation within a Python string segment."""
        if length <= 0 or current_state == STATE_DOCSTRING: return # No special rules for docstrings typically
        
        segment_full_text = text[start : start + length]
        offset = start

        is_fstring = kwargs.get('is_fstring', False)
        is_raw = kwargs.get('is_raw', False)

        escape_fmt = self.formats.get('string_escape')
        interp_fmt = self.formats.get('string_special') # For {} markers

        formats_to_apply = [] # List of (start_abs, len, format_obj)

        # 1. Find escapes (if not raw)
        if escape_fmt and not is_raw:
            try:
                for match in self.RULE_STR_ESCAPE_COMP.finditer(segment_full_text):
                     m_start, m_end = match.span()
                     formats_to_apply.append((offset + m_start, m_end - m_start, escape_fmt))
            except re.error as e: print(f"Error in Python escape regex: {e}")

        # 2. Find f-string interpolations / escaped braces
        if is_fstring and interp_fmt:
             # Must handle escapes found above - don't format interp markers over escapes?
             # Current approach: Overlap handled by `setFormat` implicitly (last one wins).
             # For {{, }}, or {expr}, format the braces themselves.
             try:
                 for match in self.RULE_FSTR_INTERP_COMP.finditer(segment_full_text):
                     m_start_rel, m_end_rel = match.span()
                     m_start_abs = offset + m_start_rel
                     
                     if match.group(1): # Escaped {{
                         # Style as interpolation marker? Or let escape rule handle '\'? Ambiguous. Style as marker.
                         formats_to_apply.append((m_start_abs, 2, interp_fmt))
                     elif match.group(2): # Escaped }}
                         formats_to_apply.append((m_start_abs, 2, interp_fmt))
                     elif match.group(3): # Interpolation {expr}
                         # Highlight opening {
                         formats_to_apply.append((m_start_abs, 1, interp_fmt))
                         # Highlight closing } - m_end is *after* the closing brace
                         formats_to_apply.append((offset + m_end_rel - 1, 1, interp_fmt))
                         # TODO: Could attempt basic highlighting *inside* the expression recursively? Very complex.
             except re.error as e: print(f"Error in Python f-string interp regex: {e}")

        # 3. Apply formats collected (sequential application, last wins on overlap)
        for apply_start, apply_len, fmt in formats_to_apply:
             try:
                  # Check range validity again just before applying
                  if apply_start >= start and apply_start + apply_len <= start + length:
                      if apply_start >= 0 and apply_start + apply_len <= len(text): # Check against full text len too
                         self.setFormat(apply_start, apply_len, fmt)
                  # else: Skip if calculated range falls outside original segment bounds

             except Exception as e:
                  print(f"Error applying internal Python format at {apply_start} len {apply_len}: {e}")


# ======================================================
# --- JavaScript Highlighter ---
# ======================================================
class JavaScriptHighlighter(SyntaxHighlighter):
    """Syntax highlighter for JavaScript with improved template literals."""
    def __init__(self, document: QTextDocument | None, colors: dict):
        super().__init__(document, colors)

        keywords_decl = ['class', 'function', 'const', 'let', 'var']
        keywords_ctrl = ['return', 'yield', 'continue', 'break', 'throw', 'try', 'catch', 'finally', 'debugger', 'if', 'else', 'switch', 'case', 'default', 'for', 'do', 'while']
        keywords_imp = ['import', 'export', 'from'] # 'default' can be keyword or identifier
        keywords_other = ['await', 'async', 'delete', 'in', 'instanceof', 'new', 'super', 'this', 'typeof', 'void', 'with', 'extends']
        booleans_consts = ['true', 'false', 'null', 'undefined', 'NaN', 'Infinity']
        builtins_list = [ # Common browser/Node builtins
            'Array', 'Boolean', 'Date', 'Error', 'Function', 'JSON', 'Math', 'Number', 'Object',
            'Promise', 'Proxy', 'Reflect', 'RegExp', 'String', 'Symbol', 'Set', 'Map', 'WeakSet', 'WeakMap',
            'console', 'document', 'window', 'globalThis', 'navigator', 'localStorage', 'sessionStorage',
            'isNaN', 'parseFloat', 'parseInt', 'isFinite',
            'decodeURI', 'decodeURIComponent', 'encodeURI', 'encodeURIComponent', 'escape', 'unescape',
            'fetch', 'setTimeout', 'setInterval', 'clearTimeout', 'clearInterval', 'queueMicrotask',
            'alert', 'confirm', 'prompt', 'require', 'module', 'exports', 'process', 'Buffer' ]
        special_vars = ['this', 'arguments', 'super', 'default'] # 'default' also keyword_imp

        kw_pattern = lambda words: r'\b(?:' + '|'.join(words) + r')\b'

        self.RULE_COMMENT_SINGLE = re.compile(r'//[^\n\r]*')
        # Regex literal detection: Heuristic: Avoid division operator ambiguity.
        # Match if preceded by specific chars or start-of-line/block, and content looks valid.
        # Simpler (less accurate) regex - focuses on content `/.../flags`
        # Does not reliably distinguish division operator. Needs contextual check (parser).
        # This basic version might mis-highlight division in some contexts.
        self.RULE_REGEX = re.compile(r'(\/(?![*/\s])(?:[^/[\\ \n\r]|\\.|\[(?:[^\]\\\n\r]|\\.)*\])+\/[gimyus]{0,6})')

        # Function/Method Defs - Focus on name identification
        self.RULE_FUNC_NAME_DEF = re.compile(r'\bfunction\s*\*?\s*([a-zA-Z_$][\w$]*)?\s*\(') # function [name](...)
        self.RULE_METHOD_NAME_DEF = re.compile(r'\b(get|set)\s+([a-zA-Z_$][\w$]*)\s*(?=\()') # get/set name(...)
        self.RULE_PROP_FUNC_DEF = re.compile(r'([a-zA-Z_$][\w$]*)\s*[:]\s*(?:async\s*)?function\b') # prop: function
        self.RULE_METHOD_DEF = re.compile(r'(?:^|\s)(?:async\s*\*?)\s*([a-zA-Z_$][\w$]*)\s*\((?=.*\)\s*{)') # async name(...) {
        self.RULE_CLASS_DEF = re.compile(r'\b(class)\s+([a-zA-Z_$][\w$]*)\b') # Handled also by keyword + identifier rule potentially

        self.RULE_KW_DECL = re.compile(kw_pattern(keywords_decl))
        self.RULE_KW_CTRL = re.compile(kw_pattern(keywords_ctrl))
        self.RULE_KW_IMP = re.compile(kw_pattern(keywords_imp))
        self.RULE_KW_OTHER = re.compile(kw_pattern(keywords_other))
        self.RULE_CONSTS = re.compile(kw_pattern(booleans_consts))
        self.RULE_BUILTINS = re.compile(r'(?<![\w$.])' + kw_pattern(builtins_list) + r'\b') # Avoid obj.builtin, allow console.log
        self.RULE_SPECIAL_VARS = re.compile(kw_pattern(special_vars))
        # Numbers: Hex/Oct/Bin/BigInt -> Float/Int/BigInt (Handles separators _)
        self.RULE_NUM_HEXOCTBIN = re.compile(r'\b(?:0[xX][0-9a-fA-F_]+n?|0[oO][0-7_]+n?|0[bB][01_]+n?)\b')
        self.RULE_NUM_FLOAT_INT = re.compile(r'\b(?:[0-9](?:_?[0-9]+)*(\.(?:[0-9](?:_?[0-9]+)*)?|\.)?|\.[0-9](?:_?[0-9]+)*)(?:[eE][-+]?[0-9](?:_?[0-9]+)*)?n?\b')

        self.RULE_SINGLE_QUOTE = re.compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'")
        self.RULE_DOUBLE_QUOTE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
        # Operators: Order matters (longer first)
        self.RULE_OPERATOR = re.compile(r'--|\+\+|>>>=?|>>>?=?|<<=?|\?\?=?|&&=?|\|\|=?|\*\*=?|=>|===?|!==?|[<>=]=?|[-+*/%&|^~?.=!:]') # Colon added
        self.RULE_PUNCTUATION_BRACES = re.compile(r'[\[\]\{\}]')
        self.RULE_PUNCTUATION_OTHER = re.compile(r'[(),;]') # Exclude . : handled by operator rule

        # Patterns used within apply_rules_within_range
        self.RULE_STR_ESCAPE_COMP = re.compile(r'\\(?:[nrtvfb\\\'"`$]|u\{[0-9a-fA-F]+\}|u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|\d{1,3}|.)') # More comprehensive
        self.RULE_TEMPLATE_INTERP = re.compile(r'(\$\{)|(\})|(\\\`)') # ${ , } , or escaped `

        rules = [
            (self.RULE_COMMENT_SINGLE, 'comment'),
            (self.RULE_REGEX, [('regex', 1)]), # Basic Regex group 1 /.../flags

            # Specific Function/Class names BEFORE keywords/builtins they might contain
            (self.RULE_CLASS_DEF, [('keyword_decl', 1), ('class_name', 2)]),
            (self.RULE_FUNC_NAME_DEF, [('func_name', 1)]), # Group 1 optional
            (self.RULE_METHOD_NAME_DEF, [('keyword', 1), ('func_name', 2)]), # get/set keywords too? No, func_name only
            (self.RULE_PROP_FUNC_DEF, [('html_attr_name', 1)]), # Treat prop name like attr name
            (self.RULE_METHOD_DEF, [('func_name', 1)]), # Class method shorthand name(...) {}

            # Keywords (declaration keywords may overlap with function name detection)
            (self.RULE_KW_DECL, 'keyword_decl'),
            (self.RULE_KW_CTRL, 'keyword_ctrl'),
            (self.RULE_KW_IMP, 'keyword_imp'),
            (self.RULE_KW_OTHER, 'keyword'),
            (self.RULE_CONSTS, 'special_var'),
            (self.RULE_BUILTINS, 'builtin'), # Builtins before special vars if overlap
            (self.RULE_SPECIAL_VARS, 'special_var'), # e.g., this

            (self.RULE_NUM_HEXOCTBIN, 'number'),
            (self.RULE_NUM_FLOAT_INT, 'number'),

            # String rules - override required for internal formatting
            (self.RULE_SINGLE_QUOTE, [('string', 1)]), # Content group 1
            (self.RULE_DOUBLE_QUOTE, [('string', 1)]), # Content group 1

            # Operators and Punctuation last
            (self.RULE_OPERATOR, 'operator'),
            (self.RULE_PUNCTUATION_BRACES, 'brace'),
            (self.RULE_PUNCTUATION_OTHER, 'punctuation'),
        ]
        self.single_line_rules = rules

        self.multiline_triggers = {
             'comment': {
                 'start': re.compile(r'/\*(?!\*)'), # Standard block comment /* ... */
                 'end': re.compile(r'\*/'),
                 'state': STATE_MULTILINE_COMMENT, 'format_key':'comment', 'priority': 15,
                 'internal_format':'comment'
             },
            # Potential JSDoc /** ... */ highlighting can be added similarly
            # 'jsdoc': {
            #      'start': re.compile(r'/\*\*'), 'end': re.compile(r'\*/'),
            #      'state': STATE_JSDOC, # Requires new state constant
            #      'format_key':'comment', 'internal_format': 'comment', 'priority': 20,
            #      # Might override apply_rules_within_range for @param etc.
            # },
             'template_literal': {
                 'start': re.compile(r'`'), 'end': re.compile(r'`'),
                 'state': STATE_TEMPLATE_LITERAL,
                 'format_key': 'string_special', # Use special format for backticks
                 'internal_format': 'string', # Base style inside is string
                 'priority': 10 # Relatively high prio
             },
        }

    # Override to handle strings and trigger internal rules
    def _apply_single_line_match(self, match_info: dict, text: str, applied_range: list[bool]) -> bool:
        match = match_info['match']
        rule_pattern = match.re
        applied = False

        # Special handling for string rules (single/double quotes)
        if rule_pattern == self.RULE_SINGLE_QUOTE or rule_pattern == self.RULE_DOUBLE_QUOTE:
            content_group_idx = 1
            # Apply base string format to content first
            applied_base = self._apply_format_to_group(match_info, content_group_idx, 'string', text, applied_range)
            applied = applied or applied_base

            # If base was applied, find the effective range and apply internal rules (escapes)
            if applied_base:
                 content_start, content_end = match.start(content_group_idx), match.end(content_group_idx)
                 if content_start != -1 and content_end > content_start:
                     # Find first/last index actually formatted in this step (simple linear scan)
                     first = -1; last = -1
                     for k in range(content_start, content_end):
                          # Need reliable way to know if applied_range[k] was set by *this specific* call.
                          # Assume for now it was, if it's true.
                         if k < len(applied_range) and applied_range[k]:
                             if first == -1: first = k
                             last = k
                     if first != -1:
                          internal_start = first
                          internal_len = (last - first) + 1
                          self.apply_rules_within_range(text, internal_start, internal_len, STATE_DEFAULT) # State DEFAULT signals regular string
            return applied

        # Explicit handling for specific named groups if needed (e.g., function names)
        elif rule_pattern in [self.RULE_CLASS_DEF, self.RULE_FUNC_NAME_DEF, self.RULE_METHOD_NAME_DEF, self.RULE_PROP_FUNC_DEF, self.RULE_METHOD_DEF, self.RULE_REGEX]:
             # Use the default implementation which handles listed format tuples [(key, group), ...]
             return super()._apply_single_line_match(match_info, text, applied_range)
        
        # Handle simple regex format differently? Group 1 only for RULE_REGEX
        # elif rule_pattern == self.RULE_REGEX:
        #    applied = self._apply_format_to_group(match_info, 1, 'regex', text, applied_range)
        #    return applied

        else:
            # Fallback to default implementation for all other rules
            return super()._apply_single_line_match(match_info, text, applied_range)

    # Use helper method for applying format to a group (defined in Python section, assumed available)
    # Needs `self.` prefix if called here.

    # Define JS specific helper if needed or rely on one potentially moved to base class
    def _apply_format_to_group(self, *args, **kwargs):
        # Assume a reusable helper exists, potentially from Python or moved to base class
        # For safety, duplicate if necessary, but best to have one shared implementation.
        # Let's assume the Python one is reusable/moved.
        
        # PythonHighlighter._apply_format_to_group(self, *args, **kwargs) # Incorrect structure
        
        # Correct way if helper IS NOT in base class: Redefine it here.
        # Correct way if helper IS in base class: Call super()._apply_format_to_group(...)
        # --- Re-implementing for clarity if not moved to base ---
        match_info = args[0]
        group_index = args[1]
        format_key = args[2]
        text = args[3]
        applied_range = args[4]

        match = match_info['match']
        if format_key not in self.formats: return False
        try:
            group_start, group_end = match.start(group_index), match.end(group_index)
        except IndexError: return False
        except ValueError: return False
        if group_start == -1 or group_end == -1 or group_end <= group_start: return False

        applied_group = False
        current_pos = group_start
        while current_pos < group_end:
            while current_pos < group_end and (current_pos >= len(applied_range) or applied_range[current_pos]): current_pos += 1
            if current_pos >= group_end: break
            segment_start = current_pos
            segment_end = segment_start
            while segment_end < group_end and (segment_end < len(applied_range) and not applied_range[segment_end]): segment_end += 1
            apply_len = segment_end - segment_start
            if apply_len > 0:
                try:
                    if segment_start >= 0 and segment_start + apply_len <= len(text):
                         self.setFormat(segment_start, apply_len, self.formats[format_key])
                         for k in range(segment_start, segment_end):
                             if k < len(applied_range): applied_range[k] = True
                         applied_group = True
                except Exception as e: print(f"Error in JS _apply_format_to_group: {e}"); break
            current_pos = segment_end
        return applied_group
        # --- End Re-implementation ---


    # Override for multi-line JS types
    def apply_multiline_format(self, text: str, start_index: int, trigger: dict, trigger_key: str, is_continuation: bool) -> tuple[int, bool]:
         """Handles JS multiline constructs, calling internal rules for template literals."""
         consumed_len, ended_on_line = super().apply_multiline_format(text, start_index, trigger, trigger_key, is_continuation)

         # If template literal content was potentially formatted, apply internal rules over it
         if consumed_len > 0 and trigger['state'] == STATE_TEMPLATE_LITERAL:
             # Calculate content span based on whether it started or continued, and if it ended
             content_start_offset = start_index if is_continuation else trigger['start'].match(text, start_index).end() if trigger['start'].match(text, start_index) else start_index
             
             total_consumed_end = start_index + consumed_len
             
             content_end_offset = total_consumed_end
             if ended_on_line and trigger.get('end'):
                  end_match = trigger['end'].search(text, content_start_offset)
                  if end_match and end_match.start() >= content_start_offset:
                       content_end_offset = end_match.start() # Content ends before delimiter starts

             internal_len = content_end_offset - content_start_offset
             internal_len = max(0, internal_len) # Ensure non-negative

             if internal_len > 0:
                  # Apply interpolation/escape rules
                  self.apply_rules_within_range(text, content_start_offset, internal_len, STATE_TEMPLATE_LITERAL)

         return consumed_len, ended_on_line


    def apply_rules_within_range(self, text: str, start: int, length: int, current_state: int, **kwargs):
        """Highlight escapes and template interpolation markers within JS strings/templates."""
        if length <= 0: return
        segment = text[start : start + length]
        offset = start

        escape_fmt = self.formats.get('string_escape')
        interp_fmt = self.formats.get('string_special') # For ${ } markers
        formats_to_apply = []

        # 1. Apply escapes within regular strings (state=DEFAULT) or template literals
        if escape_fmt and current_state in [STATE_DEFAULT, STATE_TEMPLATE_LITERAL]:
             try:
                for match in self.RULE_STR_ESCAPE_COMP.finditer(segment):
                    m_start_rel, m_end_rel = match.span()
                    # Avoid applying escape fmt inside interpolation markers? Simple overlap applied last wins for now.
                    formats_to_apply.append((offset + m_start_rel, m_end_rel - m_start_rel, escape_fmt))
             except re.error as e: print(f"Error in JS escape regex: {e}")

        # 2. Apply template literal interpolation format ${expr} and escaped \`
        if interp_fmt and current_state == STATE_TEMPLATE_LITERAL:
             try:
                for match in self.RULE_TEMPLATE_INTERP.finditer(segment):
                    m_start_rel, m_end_rel = match.span()
                    m_start_abs = offset + m_start_rel
                    m_len = m_end_rel - m_start_rel

                    if match.group(1): # Start ${
                         formats_to_apply.append((m_start_abs, 2, interp_fmt))
                         # Could highlight inside {} recursively? Complex.
                    elif match.group(2): # End }
                         formats_to_apply.append((m_start_abs, 1, interp_fmt))
                    elif match.group(3): # Escaped \`
                        # Style as escape or interp? Prefer escape.
                        if escape_fmt:
                           formats_to_apply.append((m_start_abs, 2, escape_fmt))
                        else: # Fallback if escape format missing
                           formats_to_apply.append((m_start_abs, 2, interp_fmt))
             except re.error as e: print(f"Error in JS template interp regex: {e}")

        # 3. Apply formats collected
        for apply_start, apply_len, fmt in formats_to_apply:
             try:
                 # Basic overlap: last setFormat wins.
                 # Add range check for safety.
                 if apply_start >= start and apply_start + apply_len <= start + length:
                     if apply_start >= 0 and apply_start + apply_len <= len(text):
                          self.setFormat(apply_start, apply_len, fmt)
             except Exception as e: print(f"Error applying JS internal format: {e}")

# ======================================================
# --- HTML Highlighter ---
# ======================================================
class HtmlHighlighter(SyntaxHighlighter):
    """Basic syntax highlighter for HTML, using robust embedding for JS/CSS."""
    def __init__(self, document: QTextDocument | None, colors: dict):
        super().__init__(document, colors)

        # Rules focus on tags, attributes, comments, and embedded blocks detection
        rules = [
            # Entities (Highest priority)
            (re.compile(r'&(?:[a-zA-Z0-9]+|#\d+|#x[0-9a-fA-F]+);'), 'html_entity'),
            # DOCTYPE (Treat as comment)
            (re.compile(r'<!DOCTYPE[^>]*>', re.IGNORECASE), 'comment'),

            # Tag delimiters (complex first, then simple)
            (re.compile(r'</?'), 'html_tag'), # Opening bracket(s) </ or <
            (re.compile(r'/?>'), 'html_tag'), # Closing bracket(s) /> or >

             # Tag name (low priority) - after < or </ (allowing optional whitespace)
             # Use simpler non-lookbehind: capture bracket then name
             # Rule 1: <tagname or </tagname
             (re.compile(r'(</?)\s*([a-zA-Z][\w:\-]*)'), [('html_tag', 1), ('html_tag', 2)]), # Format both bracket and name as tag

            # Attribute values (quoted, high priority after entities/delimiters)
            (re.compile(r'"([^"]*)"'), 'html_attr_value'), # Double quotes content included
            (re.compile(r"'([^']*)'"), 'html_attr_value'), # Single quotes content included

            # Attribute name (simple) - word followed by = (with optional space)
            (re.compile(r'\b([a-zA-Z_:][\w.\-:]*)\s*(?==)'), ('html_attr_name', 1)), # Allow namespace: etc.

            # Equals sign (lower priority)
            (re.compile(r'(=)'), 'operator'),
        ]
        self.single_line_rules = rules

        # Note: The HTML rules above are basic. A robust HTML highlighter often needs
        # more context awareness (e.g., distinguishing content text from tags/attrs).
        # The embedding mechanism is the main focus here.

        self.multiline_triggers = {
             'comment': {
                 'start': re.compile(r'<!--'), 'end': re.compile(r'-->'),
                 'state': STATE_MULTILINE_COMMENT, 'format_key': 'comment',
                 'internal_format': 'comment', 'priority': 5
             },
             # Embedded Script: Requires matching <script ...> tag structure carefully.
             # Using non-greedy match for attributes before '>'. Case-insensitive. DOTALL allows multiline tags.
             'script_tag': {
                 'start': re.compile(r'<script(?:\s[^>]*)?>', re.IGNORECASE | re.DOTALL), # Match <script ... >
                 'end': re.compile(r'</script\s*>', re.IGNORECASE),
                 'state': STATE_EMBEDDED_JS_IN_HTML,
                 'format_key': 'html_tag',        # Format the <script> and </script> tags themselves
                 'internal_format': None,         # Content handled entirely by sub-highlighter
                 'sub_highlighter': {'factory': JavaScriptHighlighter}, # Embed JS
                 'priority': 10
             },
             # Embedded Style
             'style_tag': {
                  'start': re.compile(r'<style(?:\s[^>]*)?>', re.IGNORECASE | re.DOTALL),
                  'end': re.compile(r'</style\s*>', re.IGNORECASE),
                  'state': STATE_EMBEDDED_CSS_IN_HTML,
                  'format_key': 'html_tag',
                  'internal_format': None,
                  'sub_highlighter': {'factory': CssHighlighter}, # Embed CSS
                  'priority': 10
             }
             # Could add triggers for on<event>="...JS..." attributes; requires parsing attribute values.
        }

    # Override needed for HTML if default single-line logic is insufficient (e.g., distinguish tag content text).
    # For this example focusing on embedding, the default logic + rules might be sufficient.


# ======================================================
# --- CSS Highlighter --- 
# ======================================================
class CssHighlighter(SyntaxHighlighter):
    """Basic syntax highlighter for CSS."""
    def __init__(self, document: QTextDocument | None, colors: dict):
        super().__init__(document, colors)

        # Vocabulary for CSS (can be expanded)
        css_properties_common = [
            'align-content', 'align-items', 'align-self', 'all', 'animation', 'animation-delay',
            'animation-direction', 'animation-duration', 'animation-fill-mode', 'animation-iteration-count',
            'animation-name', 'animation-play-state', 'animation-timing-function', 'backdrop-filter',
            'backface-visibility', 'background', 'background-attachment', 'background-blend-mode',
            'background-clip', 'background-color', 'background-image', 'background-origin', 'background-position',
            'background-repeat', 'background-size', 'border', 'border-bottom', 'border-bottom-color',
            'border-bottom-left-radius', 'border-bottom-right-radius', 'border-bottom-style', 'border-bottom-width',
            'border-collapse', 'border-color', 'border-image', 'border-image-outset', 'border-image-repeat',
            'border-image-slice', 'border-image-source', 'border-image-width', 'border-left', 'border-left-color',
            'border-left-style', 'border-left-width', 'border-radius', 'border-right', 'border-right-color',
            'border-right-style', 'border-right-width', 'border-spacing', 'border-style', 'border-top',
            'border-top-color', 'border-top-left-radius', 'border-top-right-radius', 'border-top-style',
            'border-top-width', 'border-width', 'bottom', 'box-shadow', 'box-sizing', 'break-after', 'break-before',
            'break-inside', 'caption-side', 'caret-color', 'clear', 'clip', 'clip-path', 'color', 'column-count',
            'column-fill', 'column-gap', 'column-rule', 'column-rule-color', 'column-rule-style',
            'column-rule-width', 'column-span', 'column-width', 'columns', 'content', 'counter-increment',
            'counter-reset', 'cursor', 'direction', 'display', 'empty-cells', 'filter', 'flex', 'flex-basis',
            'flex-direction', 'flex-flow', 'flex-grow', 'flex-shrink', 'flex-wrap', 'float', 'font', 'font-family',
            'font-feature-settings', 'font-kerning', 'font-language-override', 'font-optical-sizing', 'font-size',
            'font-size-adjust', 'font-stretch', 'font-style', 'font-synthesis', 'font-variant', 'font-variant-caps',
            'font-variant-east-asian', 'font-variant-ligatures', 'font-variant-numeric', 'font-variant-position',
            'font-variation-settings', 'font-weight', 'gap', 'grid', 'grid-area', 'grid-auto-columns',
            'grid-auto-flow', 'grid-auto-rows', 'grid-column', 'grid-column-end', 'grid-column-gap',
            'grid-column-start', 'grid-gap', 'grid-row', 'grid-row-end', 'grid-row-gap', 'grid-row-start',
            'grid-template', 'grid-template-areas', 'grid-template-columns', 'grid-template-rows', 'hanging-punctuation',
            'height', 'hyphens', 'image-rendering', 'isolation', 'justify-content', 'left', 'letter-spacing',
            'line-break', 'line-height', 'list-style', 'list-style-image', 'list-style-position', 'list-style-type',
            'margin', 'margin-bottom', 'margin-left', 'margin-right', 'margin-top', 'mask', 'mask-clip', 'mask-composite',
            'mask-image', 'mask-mode', 'mask-origin', 'mask-position', 'mask-repeat', 'mask-size', 'mask-type',
            'max-height', 'max-width', 'min-height', 'min-width', 'mix-blend-mode', 'object-fit', 'object-position',
            'opacity', 'order', 'orphans', 'outline', 'outline-color', 'outline-offset', 'outline-style',
            'outline-width', 'overflow', 'overflow-wrap', 'overflow-x', 'overflow-y', 'padding', 'padding-bottom',
            'padding-left', 'padding-right', 'padding-top', 'page-break-after', 'page-break-before', 'page-break-inside',
            'perspective', 'perspective-origin', 'pointer-events', 'position', 'quotes', 'resize', 'right', 'row-gap',
            'scroll-behavior', 'scroll-margin', 'scroll-padding', 'scroll-snap-align', 'scroll-snap-stop',
            'scroll-snap-type', 'shape-image-threshold', 'shape-margin', 'shape-outside', 'tab-size', 'table-layout',
            'text-align', 'text-align-last', 'text-combine-upright', 'text-decoration', 'text-decoration-color',
            'text-decoration-line', 'text-decoration-style', 'text-emphasis', 'text-emphasis-color',
            'text-emphasis-position', 'text-emphasis-style', 'text-indent', 'text-justify', 'text-orientation',
            'text-overflow', 'text-rendering', 'text-shadow', 'text-transform', 'text-underline-offset',
            'text-underline-position', 'top', 'transform', 'transform-box', 'transform-origin', 'transform-style',
            'transition', 'transition-delay', 'transition-duration', 'transition-property', 'transition-timing-function',
            'unicode-bidi', 'user-select', 'vertical-align', 'visibility', 'white-space', 'widows', 'width', 'will-change',
            'word-break', 'word-spacing', 'word-wrap', 'writing-mode', 'z-index'
            ]
        css_values_common = [ # Keywords and common values
            'absolute', 'relative', 'fixed', 'static', 'sticky', 'auto', 'inherit', 'initial', 'unset', 'revert',
            'block', 'inline', 'inline-block', 'flex', 'inline-flex', 'grid', 'inline-grid', 'none', 'contents',
            'list-item', 'table', 'table-cell', 'table-row', 'flow-root',
            'left', 'right', 'center', 'top', 'bottom', 'baseline', 'middle', 'sub', 'super', 'text-top', 'text-bottom',
            'start', 'end', 'stretch', 'space-between', 'space-around', 'space-evenly',
            'normal', 'bold', 'bolder', 'lighter', 'italic', 'oblique',
            'solid', 'dashed', 'dotted', 'double', 'groove', 'ridge', 'inset', 'outset',
            'visible', 'hidden', 'scroll', 'clip', 'collapse', 'pointer', 'default', 'grab', 'move', 'crosshair',
            'uppercase', 'lowercase', 'capitalize',
            'transparent', 'currentColor', 'black', 'silver', 'gray', 'white', 'maroon', 'red', 'purple', 'fuchsia',
            'green', 'lime', 'olive', 'yellow', 'navy', 'blue', 'teal', 'aqua'
            ]
        css_functions_common = [
            'attr', 'calc', 'clamp', 'env', 'hsl', 'hsla', 'hwb', 'lab', 'lch', 'max', 'min', 'rgb', 'rgba', 'url', 'var',
             'linear-gradient', 'radial-gradient', 'repeating-linear-gradient', 'repeating-radial-gradient',
             'conic-gradient', 'repeating-conic-gradient',
             'blur', 'brightness', 'contrast', 'drop-shadow', 'grayscale', 'hue-rotate', 'invert', 'opacity',
             'saturate', 'sepia',
             'matrix', 'perspective', 'rotate', 'rotate3d', 'rotateX', 'rotateY', 'rotateZ',
             'scale', 'scale3d', 'scaleX', 'scaleY', 'scaleZ',
             'skew', 'skewX', 'skewY', 'translate', 'translate3d', 'translateX', 'translateY', 'translateZ',
             'path', 'polygon', 'circle', 'ellipse', 'inset',
             'cubic-bezier', 'steps'
            ]
        css_at_rules = [
            'charset', 'import', 'namespace', 'media', 'supports', 'document', 'page', 'font-face',
            'keyframes', 'viewport', 'counter-style', 'font-feature-values', 'property', 'layer'
        ]
        common_elements = ['html','body','div','span','p','a','img','h1','h2','h3','h4','h5','h6','ul','ol','li','table','tr','td','th','thead','tbody','tfoot','form','input','button','label','select','option','textarea','header','footer','nav','main','article','section','aside', 'video', 'audio', 'canvas', 'svg']

        # Use (?i) for case-insensitivity where appropriate or re.IGNORECASE flag
        kw_pattern_b = lambda words: r'\b(?:' + '|'.join(words) + r')\b' # Boundary checks
        kw_pattern_bi = lambda words: r'\b(?:' + '|'.join(words) + r')\b' # Assumes IGNORECASE flag later

        rules = [
            # Selectors (Order: IDs > Attrs/Classes > Pseudos > Elements > *)
            # Ensure context to avoid matching in values/comments
            # ID #my-id
            (re.compile(r'(?<![\w\-])(#[\w\-]+)'), ('css_selector', 1)),
            # Attribute Selectors [...] (simplified: just brackets + content as selector)
            (re.compile(r'(\[[^\]]+\])'), 'css_selector'),
            # Class .my-class
            (re.compile(r'(?<![\w\-])(\.[\w\-]+)'), ('css_selector', 1)),
            # Pseudo-classes/elements :hover, ::before, :nth-child(..)
            (re.compile(r'(::?[\w\-]+)(?=\()'), 'css_selector'), # Functional pseudo, match name
            (re.compile(r'(::?[\w\-]+)\b'), 'css_selector'),     # Non-functional pseudo
            # Common element names (case insensitive)
            (re.compile(kw_pattern_bi(common_elements), re.IGNORECASE), 'css_selector'),
            # Universal Selector * (needs context)
            (re.compile(r'(?<![\w\-])([*])(?!\w)'), 'css_selector'),

            # At-Rules (@...) (case insensitive)
            (re.compile(r'(@' + '|'.join(css_at_rules) + r')\b', re.IGNORECASE), ('keyword_imp', 1)),

            # Properties (name before colon, case insensitive) - improved context
            (re.compile(r'(?:^|(?<=[{;\s]))\s*([-A-Za-z][-\w]*)\s*(?=:)'), ('css_property', 1)),

            # Values: Functions, Keywords, Units, Strings, Hex Colors, Important
            # Function calls name(...) (case insensitive)
            (re.compile(kw_pattern_bi(css_functions_common) + r'\s*\(', re.IGNORECASE), 'builtin'),
            # Common keyword values (case insensitive)
            (re.compile(kw_pattern_bi(css_values_common), re.IGNORECASE), 'css_value'),
            # Units: Number followed by unit (px, em, %, etc.) or just number
            (re.compile(r'([-+]?(?:[0-9]*\.)?[0-9]+(?:[eE][-+]?[0-9]+)?)(%|\b(?:px|em|rem|vw|vh|vmin|vmax|cm|mm|in|pt|pc|ch|ex|deg|grad|rad|turn|s|ms|Hz|kHz|dpi|dpcm|dppx|fr)\b)?'), [('number', 1), ('css_value', 2)]), # Group 2 captures unit
            # Hex Colors #rgb[a], #rrggbb[aa] (case insensitive)
            (re.compile(r'(#[0-9a-fA-F]{3,8})\b'), 'number'),
             # String values ("..." or '...')
            (re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"'), 'string'),
            (re.compile(r"'([^'\\]*(?:\\.[^'\\]*)*)'"), 'string'),
            # Important flag (case insensitive)
            (re.compile(r'(!\s*important)\b', re.IGNORECASE), ('keyword_ctrl', 1)),

            # Structure / Punctuation
            (re.compile(r'[{}:;,]'), 'punctuation'),
            (re.compile(r'[>+~()\[\]/*]'), 'operator'), # Added [ ] / * as operators
        ]
        self.single_line_rules = rules

        self.multiline_triggers = {
             'comment': {
                 'start': re.compile(r'/\*'), 'end': re.compile(r'\*/'),
                 'state': STATE_MULTILINE_COMMENT, 'format_key': 'comment',
                 'internal_format': 'comment', 'priority': 20 # High prio for comments
             }
        }


# ======================================================
# --- JSON Highlighter ---
# ======================================================
class JsonHighlighter(SyntaxHighlighter):
    """Basic syntax highlighter for JSON."""
    def __init__(self, document: QTextDocument | None, colors: dict):
        super().__init__(document, colors)

        rules = [
            # Key: String literal followed by optional whitespace and a colon
            # Use lookahead for colon, format only the string key
            (re.compile(r'("[^"\\]*(?:\\.[^"\\]*)*")\s*(?=:)'), ('json_key', 1)),

            # String Value: Any other string literal (will only match if not a key)
            (re.compile(r'("[^"\\]*(?:\\.[^"\\]*)*")'), ('string', 1)), # Group 1 includes quotes? No, capture content. Correction: Whole string needed.
            # Let's correct the string rules to capture the WHOLE string including quotes.
            (re.compile(r'("([^"\\]*(?:\\.[^"\\]*)*)")\s*(?=:)'), ('json_key', 1)), # Rule 1: Key string (group 1)
            (re.compile(r'("([^"\\]*(?:\\.[^"\\]*)*)")'), ('string', 1)), # Rule 2: Value string (group 1)

            # Literals: true, false, null (strict boundaries)
            (re.compile(r'\b(true|false|null)\b'), 'special_var'),

            # Number: Integer or float, scientific notation (strict boundaries)
            (re.compile(r'\b(-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)\b'), 'number'),

            # Structure: Braces and brackets
            (re.compile(r'([\{\}\[\]])'), 'brace'),

            # Structure: Comma and Colon (colon handled by key lookahead partially)
            (re.compile(r'([:,])'), 'punctuation'),
        ]
        self.single_line_rules = rules
        self.multiline_triggers = {} # JSON has no standard multiline comments/strings

# ======================================================
# --- XML Highlighter --- 
# ======================================================
class XmlHighlighter(SyntaxHighlighter):
    """Basic syntax highlighter for XML."""
    def __init__(self, document: QTextDocument | None, colors: dict):
        super().__init__(document, colors)

        # Basic XML/HTML-like syntax rules
        # Order matters: More specific (entities, complex delimiters) first.
        rules = [
            # 1. Entities
            (re.compile(r'&(?:[a-zA-Z0-9]+|#\d+|#x[0-9a-fA-F]+);'), 'html_entity'),

            # 2. Simple DOCTYPE matching (single line) - treat as comment
            (re.compile(r'<!DOCTYPE[^>]*>', re.IGNORECASE), 'comment'),

            # 3. Processing Instruction delimiters and target
            (re.compile(r'(<\?)'), 'html_tag'),         # Opening <?
            (re.compile(r'(\?>)'), 'html_tag'),         # Closing ?>
            (re.compile(r'(?<=<\?)\s*([\w:.\-]+)'), ('keyword_imp', 1)), # PI target name (pink)

            # 4. Tag delimiters (complex first)
            (re.compile(r'(</)'), 'html_tag'),          # Opening closing tag </
            (re.compile(r'(/?>)'), 'html_tag'),          # Self-closing tag /> or closing tag > (merged)

            # 5. Tag name (after < or </, allows ns:name)
            (re.compile(r'(</?)\s*([\w:.\-]+)'), [('html_tag', 1), ('html_tag', 2)]),
            # 6. Attribute values (quoted)
            (re.compile(r'="([^"]*)"'), ('html_attr_value', 1)), # Capture value inside quotes
            (re.compile(r"='([^']*)'"), ('html_attr_value', 1)), # Capture value inside quotes
            # Format the quotes themselves as attribute value?
            # Simpler: Just format content between quotes for now.

            # Let's adjust 6 to format the whole quoted string:
            (re.compile(r'("([^"]*)")'), ('html_attr_value', 1)),
            (re.compile(r"('([^']*)')"), ('html_attr_value', 1)),

            # 7. Attribute name (allows ns:name) followed by =
            (re.compile(r'\b([\w:.\-]+)\s*(?==)'), ('html_attr_name', 1)),

            # 8. Equals sign (lower priority)
            (re.compile(r'(=)'), 'operator'),

            # 9. Remaining simple opening tag bracket '<' (lowest priority bracket)
            (re.compile(r'(<)'), 'html_tag'),
             # Simple closing bracket '>' already covered by Rule 4 '/?>'. Add stand-alone > just in case?
             # No, probably too general and would match in content. Rule 4 should cover valid >.

            # 10. Text content is implicitly unformatted (base color)
        ]
        self.single_line_rules = rules

        self.multiline_triggers = {
             'comment': {
                 'start': re.compile(r'<!--'), 'end': re.compile(r'-->'),
                 'state': STATE_MULTILINE_COMMENT,
                 'format_key': 'comment',        # Format <!-- and -->
                 'internal_format': 'comment',   # Format content inside
                 'priority': 15                  # Higher prio than tags
             },
             'cdata': {
                 'start': re.compile(r'<!\[CDATA\['), 'end': re.compile(r'\]\]>'),
                 'state': STATE_XML_CDATA,       # Use the new state
                 'format_key': 'string_special', # Format <![CDATA[ and ]]> delimiters (yellow italic)
                 'internal_format': None,        # NO formatting for content inside CDATA
                 'priority': 20                  # Highest priority
             },
             # Multi-line DOCTYPE is complex, not handled robustly here.
             # A very simple heuristic might be:
             # 'doctype_multiline': {
             #    'start': re.compile(r'<!DOCTYPE', re.IGNORECASE),
             #    'end': re.compile(r'>'), # Ends at first '>'
             #    'state': STATE_MULTILINE_COMMENT, # Reuse comment state? Or specific DOCTYPE state?
             #    'format_key': 'comment',
             #    'internal_format': 'comment', # Needs more refined internal rules for keywords/strings
             #    'priority': 18
             # }
        }
    
    # No need to override apply_rules_within_range for XML basic highlighting.
    # Base class `highlight_segment` default implementation is likely sufficient if XML
    # were embedded (though XML embedding other languages isn't standard like HTML).





# ======================================================
# --- PowerShell Highlighter ---
# ======================================================
class PowerShellHighlighter(SyntaxHighlighter):
    """Syntax highlighter for PowerShell scripts."""
    def __init__(self, document: QTextDocument | None, colors: dict):
        super().__init__(document, colors)

        # PowerShell specific vocabulary
        keywords = [
            'begin', 'break', 'catch', 'class', 'continue', 'data', 'define', 'do', 'dynamicparam', 
            'else', 'elseif', 'end', 'enum', 'exit', 'filter', 'finally', 'for', 'foreach', 'from',
            'function', 'hidden', 'if', 'in', 'param', 'process', 'return', 'switch', 'throw',
            'trap', 'try', 'until', 'using', 'var', 'while', 'workflow'
        ]
        
        operators = [
            '-and', '-as', '-band', '-bnot', '-bor', '-bxor', '-casesensitive', '-ccontains',
            '-ceq', '-cge', '-cgt', '-cle', '-clike', '-clt', '-cmatch', '-cne', '-cnotcontains',
            '-cnotlike', '-cnotmatch', '-contains', '-creplace', '-csplit', '-eq', '-exactlylike',
            '-ge', '-gt', '-icontains', '-ieq', '-ige', '-igt', '-ile', '-ilike', '-ilt', '-imatch',
            '-in', '-ine', '-inotcontains', '-inotlike', '-inotmatch', '-ireplace', '-is', '-isnot',
            '-isplit', '-join', '-le', '-like', '-lt', '-match', '-ne', '-not', '-notcontains',
            '-notin', '-notlike', '-notmatch', '-or', '-replace', '-shl', '-shr', '-split',
            '-wildcard', '-xor'
        ]
        
        common_cmdlets = [
            'Add-Content', 'Clear-Content', 'Clear-Item', 'Clear-ItemProperty', 'Copy-Item',
            'Copy-ItemProperty', 'Get-ChildItem', 'Get-Content', 'Get-Item', 'Get-ItemProperty',
            'Get-Location', 'Move-Item', 'Move-ItemProperty', 'New-Item', 'New-ItemProperty',
            'Remove-Item', 'Remove-ItemProperty', 'Rename-Item', 'Rename-ItemProperty',
            'Set-Content', 'Set-Item', 'Set-ItemProperty', 'Set-Location', 'Test-Path',
            'Write-Output', 'Write-Host', 'Import-Module', 'Export-Module', 'New-Module',
            'Get-Module', 'Select-Object', 'Where-Object', 'ForEach-Object',
            'ConvertTo-Json', 'ConvertFrom-Json', 'ConvertTo-Csv', 'ConvertFrom-Csv',
            'Invoke-WebRequest', 'Invoke-RestMethod', 'Invoke-Command', 'Invoke-Expression',
            'Get-Process', 'Start-Process', 'Stop-Process'
        ]
        
        automatic_vars = [
            '$args', '$error', '$false', '$foreach', '$home', '$host', '$input', '$lastexitcode',
            '$matches', '$myinvocation', '$nestedpromptlevel', '$null', '$pid', '$profile', '$psboundparameters',
            '$pscmdlet', '$pscommandpath', '$psculture', '$psdebugcontext', '$pshome', '$psitem',
            '$psscriptroot', '$pssenderinfo', '$psuiculture', '$psversiontable', '$pwd', '$sender',
            '$shellid', '$stacktrace', '$this', '$true'
        ]
        
        # Regular expressions patterns
        kw_pattern = lambda words: r'\b(?:' + '|'.join(words) + r')\b'
        
        self.RULE_COMMENT_SINGLE = re.compile(r'#[^\n]*')
        self.RULE_VARIABLE = re.compile(r'(\$[\w:]+|\${[^}]*})')
        self.RULE_CMDLET = re.compile(r'\b([A-Z][a-z]+-[A-Z][a-z]+)\b')
        self.RULE_PARAMETER = re.compile(r'\B(-[a-zA-Z_][\w-]*)\b')
        self.RULE_KW = re.compile(kw_pattern(keywords), re.IGNORECASE)
        self.RULE_OP = re.compile(kw_pattern(operators), re.IGNORECASE)
        self.RULE_COMMON_CMDLETS = re.compile(kw_pattern(common_cmdlets), re.IGNORECASE)
        self.RULE_AUTO_VARS = re.compile(kw_pattern(automatic_vars), re.IGNORECASE)
        self.RULE_NUMBER = re.compile(r'\b((?:0[xX][0-9a-fA-F]+)|(?:(?:\b[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?))\b')
        self.RULE_DOUBLE_QUOTED_STRING = re.compile(r'"([^"\\]|\\.|`[^"])*"')
        self.RULE_SINGLE_QUOTED_STRING = re.compile(r"'([^'\\]|\\.|`[^'])*'")
        self.RULE_BRACES = re.compile(r'[\(\)\{\}\[\]]')
        self.RULE_PUNCTUATION = re.compile(r'[;,\.]')
        self.RULE_PIPE = re.compile(r'\|')
        self.RULE_SPECIAL_CHARS = re.compile(r'[@%!&=\+\-\*/<>\^\?]')
        
        # Single line rules
        rules = [
            (self.RULE_COMMENT_SINGLE, 'comment'),
            (self.RULE_VARIABLE, 'special_var'),
            (self.RULE_CMDLET, 'func_name'),
            (self.RULE_COMMON_CMDLETS, 'func_name'),
            (self.RULE_PARAMETER, 'keyword'),
            (self.RULE_KW, 'keyword_ctrl'),
            (self.RULE_OP, 'operator'),
            (self.RULE_AUTO_VARS, 'special_var'),
            (self.RULE_NUMBER, 'number'),
            (self.RULE_DOUBLE_QUOTED_STRING, 'string'),
            (self.RULE_SINGLE_QUOTED_STRING, 'string'),
            (self.RULE_BRACES, 'brace'),
            (self.RULE_PUNCTUATION, 'punctuation'),
            (self.RULE_PIPE, 'operator'),
            (self.RULE_SPECIAL_CHARS, 'operator'),
        ]
        self.single_line_rules = rules
        
        # Multi-line triggers for comments and here-strings
        self.multiline_triggers = {
            'comment': {
                'start': re.compile(r'<#'),
                'end': re.compile(r'#>'),
                'state': STATE_MULTILINE_COMMENT,
                'format_key': 'comment',
                'internal_format': 'comment',
                'priority': 15
            },
            'here_string_double': {
                'start': re.compile(r'@"[\r\n]'),
                'end': re.compile(r'[\r\n]"@'),
                'state': STATE_TRIPLE_QUOTE_STRING,  # Reuse this state
                'format_key': 'string_special',
                'internal_format': 'string',
                'priority': 10
            },
            'here_string_single': {
                'start': re.compile(r"@'[\r\n]"),
                'end': re.compile(r"[\r\n]'@"),
                'state': STATE_TRIPLE_QUOTE_STRING,  # Reuse this state
                'format_key': 'string_special',
                'internal_format': 'string',
                'priority': 10
            }
        }
    
    def apply_rules_within_range(self, text: str, start: int, length: int, current_state: int, **kwargs):
        """Handles special formatting within strings, like variable interpolation in double-quoted strings."""
        if length <= 0: return
        
        # Only process variable interpolation in double-quoted strings and here-strings
        if current_state == STATE_DEFAULT or current_state == STATE_TRIPLE_QUOTE_STRING:
            segment = text[start : start + length]
            offset = start
            
            # Look for variable references in strings
            variable_fmt = self.formats.get('special_var')
            if variable_fmt:
                try:
                    for match in self.RULE_VARIABLE.finditer(segment):
                        m_start_rel, m_end_rel = match.span()
                        m_start_abs = offset + m_start_rel
                        m_len = m_end_rel - m_start_rel
                        
                        if m_len > 0:
                            self.setFormat(m_start_abs, m_len, variable_fmt)
                except re.error as e:
                    print(f"Error in PowerShell variable interpolation regex: {e}")
                except Exception as e:
                    print(f"Error applying PowerShell variable format: {e}")

# ======================================================
# --- Bash Highlighter ---
# ======================================================
class BashHighlighter(SyntaxHighlighter):
    """Syntax highlighter for Bash/sh scripts."""
    def __init__(self, document: QTextDocument | None, colors: dict):
        super().__init__(document, colors)

        # Bash specific vocabulary
        keywords = [
            'if', 'then', 'else', 'elif', 'fi', 'case', 'esac', 'for', 'select',
            'while', 'until', 'do', 'done', 'in', 'function', 'time', 'coproc',
            'return', 'continue', 'break', 'shift', 'declare', 'local', 'export',
            'readonly', 'set', 'unset', 'trap', 'let', 'eval'
        ]
        
        builtins = [
            'echo', 'printf', 'read', 'cd', 'pwd', 'pushd', 'popd', 'dirs',
            'ls', 'mkdir', 'rmdir', 'touch', 'cp', 'mv', 'rm', 'ln', 'chmod',
            'chown', 'chgrp', 'find', 'grep', 'sed', 'awk', 'cut', 'sort',
            'uniq', 'wc', 'head', 'tail', 'test', 'cat', 'tee', 'basename',
            'dirname', 'source', 'exit', 'exec', 'command', 'type', 'which',
            'getopts', 'wait', 'jobs', 'bg', 'fg', 'kill', 'sleep', 'history',
            'ulimit', 'umask', 'alias', 'unalias', 'help', 'sudo', 'su'
        ]
        
        # Regular expressions patterns
        kw_pattern = lambda words: r'\b(?:' + '|'.join(words) + r')\b'
        
        self.RULE_COMMENT = re.compile(r'#[^\n]*')
        self.RULE_VARIABLE = re.compile(r'(\$[\w\d_]+|\$\{[^}]*\})')
        self.RULE_PARAM_EXPANSION = re.compile(r'\$\{[^}]*\}')
        self.RULE_CMD_SUBST_BACKTICK = re.compile(r'`[^`]*`')
        self.RULE_CMD_SUBST_DOLLAR = re.compile(r'\$\([^)]*\)')
        self.RULE_ARITHMETIC_EXPR = re.compile(r'\$\(\([^)]*\)\)')
        self.RULE_FUNCTION_DEF = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*\)')
        self.RULE_KW = re.compile(kw_pattern(keywords))
        self.RULE_BUILTINS = re.compile(kw_pattern(builtins))
        
        # Special vars - handle these separately to avoid regex metachars
        self.RULE_SPECIAL_VARS = re.compile(r'(\$\?|\$!|\$\$|\$#|\$@|\$\*|\$-|\$_|\$[0-9]|IFS|PATH|HOME|PWD|OLDPWD|SHELL|BASH_VERSION|PIPESTATUS|HOSTNAME|RANDOM|LINENO|SECONDS|BASH_COMMAND)')
        
        self.RULE_NUMBER = re.compile(r'\b(?:[0-9]+)\b')
        self.RULE_HEX_NUMBER = re.compile(r'\b0[xX][0-9a-fA-F]+\b')
        self.RULE_DOUBLE_QUOTED_STRING = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"')
        self.RULE_SINGLE_QUOTED_STRING = re.compile(r"'[^']*'")
        self.RULE_BRACES = re.compile(r'[\(\)\{\}\[\]]')
        self.RULE_REDIRECT = re.compile(r'[<>]+&?\d*')
        self.RULE_PIPE = re.compile(r'\|+')
        self.RULE_LOGICAL_OP = re.compile(r'&&|\|\||;+')
        self.RULE_SPECIAL_CHARS = re.compile(r'[=\+\-\*/%!&\^~]')
        
        # Single line rules
        rules = [
            (self.RULE_COMMENT, 'comment'),
            (self.RULE_FUNCTION_DEF, ('func_name', 1)),
            (self.RULE_KW, 'keyword_ctrl'),
            (self.RULE_BUILTINS, 'builtin'),
            (self.RULE_VARIABLE, 'special_var'),
            (self.RULE_PARAM_EXPANSION, 'special_var'),
            (self.RULE_CMD_SUBST_BACKTICK, 'string_special'),
            (self.RULE_CMD_SUBST_DOLLAR, 'string_special'),
            (self.RULE_ARITHMETIC_EXPR, 'string_special'),
            (self.RULE_SPECIAL_VARS, 'special_var'),
            (self.RULE_NUMBER, 'number'),
            (self.RULE_HEX_NUMBER, 'number'),
            (self.RULE_DOUBLE_QUOTED_STRING, 'string'),
            (self.RULE_SINGLE_QUOTED_STRING, 'string'),
            (self.RULE_BRACES, 'brace'),
            (self.RULE_REDIRECT, 'operator'),
            (self.RULE_PIPE, 'operator'),
            (self.RULE_LOGICAL_OP, 'operator'),
            (self.RULE_SPECIAL_CHARS, 'operator'),
        ]
        self.single_line_rules = rules
        
        # Multi-line triggers for heredocs
        self.multiline_triggers = {
            'heredoc': {
                'start': re.compile(r'<<-?\s*(["\']?)(\w+)\1'),
                'end': re.compile(r'^\s*\w+$'),  # Will be dynamically updated in apply_multiline_format
                'state': STATE_TRIPLE_QUOTE_STRING,  # Reuse this state
                'format_key': 'string_special',
                'internal_format': 'string',
                'priority': 10
            }
        }
    
    def apply_multiline_format(self, text: str, start_index: int, trigger: dict, trigger_key: str, is_continuation: bool) -> tuple[int, bool]:
        """Handle heredoc delimiter matching with proper boundary"""
        if trigger_key == 'heredoc' and not is_continuation:
            # Extract the delimiter from the start pattern
            start_match = trigger['start'].search(text, start_index)
            if start_match:
                delimiter = start_match.group(2)
                # Modify the end pattern to match the exact delimiter
                trigger['end'] = re.compile(r'^\s*(' + re.escape(delimiter) + r')$')
        
        return super().apply_multiline_format(text, start_index, trigger, trigger_key, is_continuation)
    
    def apply_rules_within_range(self, text: str, start: int, length: int, current_state: int, **kwargs):
        """Handles variable interpolation in double-quoted strings and command substitutions"""
        if length <= 0: return
        
        segment = text[start : start + length]
        offset = start
        
        # Look for variable references in strings when in a double-quoted string or heredoc
        if current_state == STATE_DEFAULT or current_state == STATE_TRIPLE_QUOTE_STRING:
            variable_fmt = self.formats.get('special_var')
            if variable_fmt:
                try:
                    for match in self.RULE_VARIABLE.finditer(segment):
                        m_start_rel, m_end_rel = match.span()
                        m_start_abs = offset + m_start_rel
                        m_len = m_end_rel - m_start_rel
                        
                        if m_len > 0:
                            self.setFormat(m_start_abs, m_len, variable_fmt)
                except Exception as e:
                    print(f"Error applying Bash variable format: {e}")
            
            # Look for command substitutions in strings
            cmd_subst_fmt = self.formats.get('string_special')
            if cmd_subst_fmt:
                try:
                    for pattern in [self.RULE_CMD_SUBST_BACKTICK, self.RULE_CMD_SUBST_DOLLAR]:
                        for match in pattern.finditer(segment):
                            m_start_rel, m_end_rel = match.span()
                            m_start_abs = offset + m_start_rel
                            m_len = m_end_rel - m_start_rel
                            
                            if m_len > 0:
                                self.setFormat(m_start_abs, m_len, cmd_subst_fmt)
                except Exception as e:
                    print(f"Error applying Bash command substitution format: {e}")               



# ======================================================
# --- Bash Highlighter ---
# ======================================================
class BashHighlighter(SyntaxHighlighter):
    """Syntax highlighter for Bash/sh scripts."""
    def __init__(self, document: QTextDocument | None, colors: dict):
        super().__init__(document, colors)

        # Bash specific vocabulary
        keywords = [
            'if', 'then', 'else', 'elif', 'fi', 'case', 'esac', 'for', 'select',
            'while', 'until', 'do', 'done', 'in', 'function', 'time', 'coproc',
            'return', 'continue', 'break', 'shift', 'declare', 'local', 'export',
            'readonly', 'set', 'unset', 'trap', 'let', 'eval'
        ]
        
        builtins = [
            'echo', 'printf', 'read', 'cd', 'pwd', 'pushd', 'popd', 'dirs',
            'ls', 'mkdir', 'rmdir', 'touch', 'cp', 'mv', 'rm', 'ln', 'chmod',
            'chown', 'chgrp', 'find', 'grep', 'sed', 'awk', 'cut', 'sort',
            'uniq', 'wc', 'head', 'tail', 'test', 'cat', 'tee', 'basename',
            'dirname', 'source', 'exit', 'exec', 'command', 'type', 'which',
            'getopts', 'wait', 'jobs', 'bg', 'fg', 'kill', 'sleep', 'history',
            'ulimit', 'umask', 'alias', 'unalias', 'help', 'sudo', 'su'
        ]
        
        # Regular expressions patterns
        kw_pattern = lambda words: r'\b(?:' + '|'.join(words) + r')\b'
        
        self.RULE_COMMENT = re.compile(r'#[^\n]*')
        self.RULE_VARIABLE = re.compile(r'(\$[\w\d_]+|\$\{[^}]*\})')
        self.RULE_PARAM_EXPANSION = re.compile(r'\$\{[^}]*\}')
        self.RULE_CMD_SUBST_BACKTICK = re.compile(r'`[^`]*`')
        self.RULE_CMD_SUBST_DOLLAR = re.compile(r'\$\([^)]*\)')
        self.RULE_ARITHMETIC_EXPR = re.compile(r'\$\(\([^)]*\)\)')
        self.RULE_FUNCTION_DEF = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\(\s*\)')
        self.RULE_KW = re.compile(kw_pattern(keywords))
        self.RULE_BUILTINS = re.compile(kw_pattern(builtins))
        
        # Special vars - handle these separately to avoid regex metachars
        self.RULE_SPECIAL_VARS = re.compile(r'(\$\?|\$!|\$\$|\$#|\$@|\$\*|\$-|\$_|\$[0-9]|IFS|PATH|HOME|PWD|OLDPWD|SHELL|BASH_VERSION|PIPESTATUS|HOSTNAME|RANDOM|LINENO|SECONDS|BASH_COMMAND)')
        
        self.RULE_NUMBER = re.compile(r'\b(?:[0-9]+)\b')
        self.RULE_HEX_NUMBER = re.compile(r'\b0[xX][0-9a-fA-F]+\b')
        self.RULE_DOUBLE_QUOTED_STRING = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"')
        self.RULE_SINGLE_QUOTED_STRING = re.compile(r"'[^']*'")
        self.RULE_BRACES = re.compile(r'[\(\)\{\}\[\]]')
        self.RULE_REDIRECT = re.compile(r'[<>]+&?\d*')
        self.RULE_PIPE = re.compile(r'\|+')
        self.RULE_LOGICAL_OP = re.compile(r'&&|\|\||;+')
        self.RULE_SPECIAL_CHARS = re.compile(r'[=\+\-\*/%!&\^~]')
        
        # Single line rules
        rules = [
            (self.RULE_COMMENT, 'comment'),
            (self.RULE_FUNCTION_DEF, ('func_name', 1)),
            (self.RULE_KW, 'keyword_ctrl'),
            (self.RULE_BUILTINS, 'builtin'),
            (self.RULE_VARIABLE, 'special_var'),
            (self.RULE_PARAM_EXPANSION, 'special_var'),
            (self.RULE_CMD_SUBST_BACKTICK, 'string_special'),
            (self.RULE_CMD_SUBST_DOLLAR, 'string_special'),
            (self.RULE_ARITHMETIC_EXPR, 'string_special'),
            (self.RULE_SPECIAL_VARS, 'special_var'),
            (self.RULE_NUMBER, 'number'),
            (self.RULE_HEX_NUMBER, 'number'),
            (self.RULE_DOUBLE_QUOTED_STRING, 'string'),
            (self.RULE_SINGLE_QUOTED_STRING, 'string'),
            (self.RULE_BRACES, 'brace'),
            (self.RULE_REDIRECT, 'operator'),
            (self.RULE_PIPE, 'operator'),
            (self.RULE_LOGICAL_OP, 'operator'),
            (self.RULE_SPECIAL_CHARS, 'operator'),
        ]
        self.single_line_rules = rules
        
        # Multi-line triggers for heredocs
        self.multiline_triggers = {
            'heredoc': {
                'start': re.compile(r'<<-?\s*(["\']?)(\w+)\1'),
                'end': re.compile(r'^\s*\w+$'),  # Will be dynamically updated in apply_multiline_format
                'state': STATE_TRIPLE_QUOTE_STRING,  # Reuse this state
                'format_key': 'string_special',
                'internal_format': 'string',
                'priority': 10
            }
        }
    
    def apply_multiline_format(self, text: str, start_index: int, trigger: dict, trigger_key: str, is_continuation: bool) -> tuple[int, bool]:
        """Handle heredoc delimiter matching with proper boundary"""
        if trigger_key == 'heredoc' and not is_continuation:
            # Extract the delimiter from the start pattern
            start_match = trigger['start'].search(text, start_index)
            if start_match:
                delimiter = start_match.group(2)
                # Modify the end pattern to match the exact delimiter
                trigger['end'] = re.compile(r'^\s*(' + re.escape(delimiter) + r')$')
        
        return super().apply_multiline_format(text, start_index, trigger, trigger_key, is_continuation)
    
    def apply_rules_within_range(self, text: str, start: int, length: int, current_state: int, **kwargs):
        """Handles variable interpolation in double-quoted strings and command substitutions"""
        if length <= 0: return
        
        segment = text[start : start + length]
        offset = start
        
        # Look for variable references in strings when in a double-quoted string or heredoc
        if current_state == STATE_DEFAULT or current_state == STATE_TRIPLE_QUOTE_STRING:
            variable_fmt = self.formats.get('special_var')
            if variable_fmt:
                try:
                    for match in self.RULE_VARIABLE.finditer(segment):
                        m_start_rel, m_end_rel = match.span()
                        m_start_abs = offset + m_start_rel
                        m_len = m_end_rel - m_start_rel
                        
                        if m_len > 0:
                            self.setFormat(m_start_abs, m_len, variable_fmt)
                except Exception as e:
                    print(f"Error applying Bash variable format: {e}")
            
            # Look for command substitutions in strings
            cmd_subst_fmt = self.formats.get('string_special')
            if cmd_subst_fmt:
                try:
                    for pattern in [self.RULE_CMD_SUBST_BACKTICK, self.RULE_CMD_SUBST_DOLLAR]:
                        for match in pattern.finditer(segment):
                            m_start_rel, m_end_rel = match.span()
                            m_start_abs = offset + m_start_rel
                            m_len = m_end_rel - m_start_rel
                            
                            if m_len > 0:
                                self.setFormat(m_start_abs, m_len, cmd_subst_fmt)
                except Exception as e:
                    print(f"Error applying Bash command substitution format: {e}")
# ======================================================

# ======================================================
# --- Batch File Highlighter ---
# ======================================================
class BatchHighlighter(SyntaxHighlighter):
    """Syntax highlighter for Windows Batch (.bat, .cmd) files."""
    def __init__(self, document: QTextDocument | None, colors: dict):
        super().__init__(document, colors)

        # Batch specific vocabulary
        keywords = [
            'goto', 'call', 'if', 'else', 'for', 'in', 'do', 'exit', 'setlocal', 'endlocal',
            'shift', 'cd', 'cls', 'echo', 'set', 'pause', 'rem', 'title', 'defined',
            'errorlevel', 'exist', 'choice', 'enabledelayedexpansion', 'enableextensions'
        ]
        
        commands = [
            'attrib', 'assoc', 'break', 'bcdedit', 'cacls', 'chcp', 'chdir', 'chkdsk', 'chkntfs',
            'comp', 'compact', 'convert', 'copy', 'date', 'del', 'dir', 'diskpart', 'doskey',
            'driverquery', 'endlocal', 'erase', 'fc', 'find', 'findstr', 'format', 'fsutil',
            'ftype', 'gpresult', 'icacls', 'label', 'md', 'mkdir', 'mklink', 'mode', 'more',
            'move', 'net', 'netsh', 'path', 'popd', 'print', 'prompt', 'pushd', 'rd', 'recover',
            'rename', 'ren', 'replace', 'rmdir', 'robocopy', 'sc', 'schtasks', 'setx', 'shutdown',
            'sort', 'start', 'subst', 'systeminfo', 'tasklist', 'taskkill', 'time', 'timeout',
            'tree', 'type', 'ver', 'verify', 'vol', 'xcopy', 'wmic'
        ]
        
        operators = [
            'equ', 'neq', 'lss', 'leq', 'gtr', 'geq', 'not', 'and', 'or', 'xor'
        ]
        
        # Regular expressions patterns
        kw_pattern = lambda words: r'\b(?:' + '|'.join(words) + r')\b'
        
        # Batch files are case-insensitive
        self.RULE_COMMENT = re.compile(r'(?:^|\s)(?:rem\s+.+|::.*)', re.IGNORECASE)
        self.RULE_LABEL = re.compile(r'^\s*:(\w+)')
        self.RULE_VARIABLE_USE = re.compile(r'%([^%]+)%')
        self.RULE_DELAYED_EXPANSION = re.compile(r'!([^!]+)!')
        self.RULE_SET_VARIABLE = re.compile(r'\bset\s+(?:/[aP]\s+)?([^=]+)=', re.IGNORECASE)
        self.RULE_FOR_VARIABLE = re.compile(r'\bfor\s+/[fLRD]\s+(?:%%|\$)[a-zA-Z]\s+', re.IGNORECASE)
        self.RULE_FOR_PARAMS = re.compile(r'(?:%%|\$)([a-zA-Z])')
        self.RULE_KEYWORDS = re.compile(kw_pattern(keywords), re.IGNORECASE)
        self.RULE_COMMANDS = re.compile(kw_pattern(commands), re.IGNORECASE)
        self.RULE_OPERATORS = re.compile(kw_pattern(operators), re.IGNORECASE)
        self.RULE_REDIRECT = re.compile(r'[><]&?\d*')
        self.RULE_PIPE = re.compile(r'\|')
        self.RULE_AMPERSAND = re.compile(r'&')
        self.RULE_STRING_DOUBLE = re.compile(r'"[^"]*"')
        self.RULE_ARGUMENT = re.compile(r'%(\d+)')
        self.RULE_ENVIRONMENT_VAR = re.compile(r'%(?:windir|temp|errorlevel|cd|date|time|random|path|systemroot)%', re.IGNORECASE)
        
        # Single line rules
        rules = [
            (self.RULE_COMMENT, 'comment'),
            (self.RULE_LABEL, ('func_name', 1)),
            (self.RULE_ENVIRONMENT_VAR, 'special_var'),
            (self.RULE_VARIABLE_USE, ('special_var', 1)),
            (self.RULE_DELAYED_EXPANSION, ('special_var', 1)),
            (self.RULE_SET_VARIABLE, ('html_attr_name', 1)),
            (self.RULE_FOR_PARAMS, ('special_var', 1)),
            (self.RULE_KEYWORDS, 'keyword_ctrl'),
            (self.RULE_COMMANDS, 'builtin'),
            (self.RULE_OPERATORS, 'operator'),
            (self.RULE_REDIRECT, 'operator'),
            (self.RULE_PIPE, 'operator'),
            (self.RULE_AMPERSAND, 'operator'),
            (self.RULE_STRING_DOUBLE, 'string'),
            (self.RULE_ARGUMENT, ('special_var', 1)),
        ]
        self.single_line_rules = rules
        
        # Batch files don't typically have multi-line constructs like other languages
        self.multiline_triggers = {}


# ======================================================
def get_highlighter_for_file(filepath: str | None, document: QTextDocument, colors: dict) -> SyntaxHighlighter | None:
    """
    Factory function to get the appropriate highlighter based on file extension.

    Args:
        filepath (str | None): Path to the file, used to determine extension.
        document (QTextDocument): The document to attach the highlighter to.
        colors (dict): The color theme dictionary.

    Returns:
        SyntaxHighlighter | None: An instance of the appropriate highlighter, or None.
    """
    instance = None
    highlighter_class = None

    if isinstance(filepath, str) and filepath:
        try:
            _, ext = os.path.splitext(filepath)
            ext = ext.lower()
        except Exception as e:
             print(f"Warning: Could not parse filepath '{filepath}': {e}")
             ext = None

        highlighter_map = {
            # Python
            '.py': PythonHighlighter, '.pyw': PythonHighlighter, '.pyi': PythonHighlighter,
            # JavaScript
            '.js': JavaScriptHighlighter, '.jsx': JavaScriptHighlighter, 
            '.mjs': JavaScriptHighlighter, '.cjs': JavaScriptHighlighter,
            # Web
            '.html': HtmlHighlighter, '.htm': HtmlHighlighter,
            '.css': CssHighlighter,
            # Data
            '.json': JsonHighlighter,
            '.xml': XmlHighlighter,
            # PowerShell
            '.ps1': PowerShellHighlighter, '.psm1': PowerShellHighlighter, '.psd1': PowerShellHighlighter,
            # Bash/Shell
            '.sh': BashHighlighter, '.bash': BashHighlighter, '.bashrc': BashHighlighter,
            '.bash_profile': BashHighlighter, '.zsh': BashHighlighter, '.ksh': BashHighlighter,
            '.bat': BatchHighlighter, '.cmd': BatchHighlighter,

        }

        if ext:
            highlighter_class = highlighter_map.get(ext)
            if highlighter_class:
                 print(f"Debug: Found highlighter {highlighter_class.__name__} for extension '{ext}'")
            else:
                 print(f"Debug: No specific highlighter class found for extension '{ext}'")
        else:
            print("Debug: No file extension provided or found.")

    else: # No filepath provided
        print("Debug: No filepath provided to factory function.")
        # Optionally return a default highlighter (SyntaxHighlighter base class) or None
        # Return None for now, indicating no specific highlighting applied
        highlighter_class = None

    # Instantiate the selected class, passing the necessary document and colors
    if highlighter_class:
        try:
            # Ensure the document is passed ONLY if it's valid.
            # The highlighter class __init__ should handle None if necessary for non-functional instances.
            # However, for immediate use, the factory should provide the valid document.
            if document and isinstance(document, QTextDocument):
                instance = highlighter_class(document, colors)
                print(f"Debug: Instantiated {highlighter_class.__name__}")
            else:
                 # This case should be rare if called from application context where doc exists
                 print(f"Warning: Invalid document provided to factory for {highlighter_class.__name__}. Highlighter not created.")
                 instance = None
        except Exception as e:
            print(f"Error: Failed to initialize highlighter {highlighter_class.__name__} (ext: {ext}): {e}")
            instance = None # Fallback to no highlighter on instantiation error
    else:
         # instance remains None if no class was found or specified
         pass

    return instance