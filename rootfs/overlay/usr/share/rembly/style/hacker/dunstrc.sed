s/^\( *frame_color = \).*/\1"#39ff88"/
/^\[urgency_low\]/,/^\[urgency_normal\]/{s/^\( *background = \).*/\1"#020a05"/;s/^\( *foreground = \).*/\1"#7fd9a6"/}
/^\[urgency_normal\]/,/^\[urgency_critical\]/{s/^\( *background = \).*/\1"#04100a"/;s/^\( *foreground = \).*/\1"#c9ffe0"/}
/^\[urgency_critical\]/,${s/^\( *background = \).*/\1"#39ff88"/;s/^\( *foreground = \).*/\1"#02100a"/;s/^\( *frame_color = \).*/\1"#8dffb9"/}
