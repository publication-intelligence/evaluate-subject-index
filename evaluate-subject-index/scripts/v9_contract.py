"""Cross-field checks for the V9 percentage representation; no scoring decisions."""
from decimal import Decimal, InvalidOperation


def alias(key):
    return key in {'rating', 'rating_delta', 'maximum_rating'} or key.endswith('_rating')


def scorecard_errors(row):
    errors = []
    pct, points = row.get('dimension_percentage'), row.get('weighted_contribution')
    if pct is None:
        if points is not None:
            errors.append('Unscored dimension cannot have awarded points')
    elif points is None or Decimal(points) != Decimal(pct) * Decimal(str(row['weight'])) / 100:
        errors.append('Weighted contribution differs from percentage × weight / 100')
    if 'awarded_points' in row and row['awarded_points'] != points:
        errors.append('Awarded points differ from authoritative weighted contribution')
    if 'maximum_points' in row and Decimal(row['maximum_points']) != Decimal(str(row['weight'])):
        errors.append('Maximum points differ from dimension weight')
    return errors


def density_errors(density):
    errors = []
    rows = density.get('chapter_measurements', density.get('items', []))
    total_words = 0
    total_weighted = Decimal(0)
    for row in rows:
        fit = row.get('canonical_fit_judgment', row)
        for key in ('path_fit_percentage', 'occurrence_fit_percentage', 'unit_fit_percentage', 'weighted_percentage_numerator'):
            if not isinstance(fit.get(key), str):
                errors.append(f'Density {key} must be an exact decimal string')
        if errors:
            continue
        unit = (Decimal(fit['path_fit_percentage']) + Decimal(fit['occurrence_fit_percentage'])) / 2
        words = row['indexable_source_words']
        if not isinstance(words, int) or isinstance(words, bool) or words <= 0:
            errors.append('Density requires a positive integer word denominator')
        numerator = unit * Decimal(words)
        if Decimal(fit['unit_fit_percentage']) != unit or Decimal(fit['weighted_percentage_numerator']) != numerator:
            errors.append('Density chapter percentage/numerator does not reconstruct')
        total_words += words
        total_weighted += numerator
    if not rows or total_words <= 0:
        errors.append('Density requires measured chapters')
        return errors
    if density.get('total_indexable_source_words') != total_words:
        errors.append('Density total word denominator does not reconstruct')
    if not isinstance(density.get('total_weighted_percentage_numerator'), str) or Decimal(density['total_weighted_percentage_numerator']) != total_weighted:
        errors.append('Density total weighted numerator does not reconstruct')
    for key in ('density_fit_percentage', 'fit_percentage'):
        if (key == 'density_fit_percentage' or key in density) and (not isinstance(density.get(key), str) or Decimal(density[key]) != total_weighted / Decimal(total_words)):
            errors.append(f'Density {key} does not reconstruct')
    return errors


def contract_errors(document, *, allow_semantic=False):
    errors = []
    if document.get('schema_version') == 'ohfr-v9-canonical-web-projection-v1':
        views = document['score_views']
        has_overlay = any(row['collection_id'] == 'correction_overlay' for row in document['collections'])
        expected = 'diagnostic_overlay_only' if has_overlay else 'not_applicable'
        if views['projection_adjustment_status'] != expected or views['total_delta'] != 0:
            errors.append('V9 diagnostic overlays do not produce adjusted scoring views or deltas')
    def visit(value, path=''):
        if isinstance(value, list):
            for i, item in enumerate(value):
                visit(item, f'{path}[{i}]')
        elif isinstance(value, dict):
            for key, item in value.items():
                if alias(key):
                    errors.append(f'{path}.{key}: five-point aliases are forbidden in V9')
                visit(item, f'{path}.{key}')
            if {'dimension_percentage', 'weighted_contribution'} <= value.keys() and ('weight' in value or 'dimension_weight' in value):
                row = {**value, 'weight': value.get('weight', value.get('dimension_weight'))}
                errors.extend(f'{path}: {error}' for error in scorecard_errors(row))
            if ('total_weighted_percentage_numerator' in value or value.get('collection_kind') == 'density' or ('chapter_measurements' in value and ('fit_percentage' in value or 'density_fit_percentage' in value))):
                errors.extend(f'{path}: {error}' for error in density_errors(value))
            if value.get('component_id') == 'density_fit' and 'details' in value:
                errors.extend(f'{path}: {error}' for error in density_errors(value['details']))
            if value.get('dimension_id') == 'editorial_selectivity' and ('post_cap_percentage' in value or 'substantive_selectivity_percentage' in value):
                s, d = value['substantive_selectivity_percentage'], value['density_fit_percentage']
                if allow_semantic and s is None and value.get('semantic_uncertainty'):
                    if value['substantive_points_out_of_10'] is not None or value.get('post_cap_percentage',value.get('dimension_percentage')) is not None:
                        errors.append(f'{path}: unresolved selectivity cannot assert central points or percentage')
                    if Decimal(value['density_points_out_of_5']) != Decimal(d)*5/100:
                        errors.append(f'{path}: density contribution does not reconstruct')
                    return
                if Decimal(value['substantive_points_out_of_10']) != Decimal(s) * 10 / 100 or Decimal(value['density_points_out_of_5']) != Decimal(d) * 5 / 100:
                    errors.append(f'{path}: selectivity point contributions do not reconstruct')
                percentage = value.get('post_cap_percentage', value.get('dimension_percentage'))
                if percentage is not None and Decimal(percentage) != (Decimal(s) * 10 + Decimal(d) * 5) / 15:
                    errors.append(f'{path}: selectivity percentage does not reconstruct')
    try:
        visit(document)
    except (InvalidOperation, TypeError, KeyError, ValueError) as exc:
        errors.append(f'Invalid V9 percentage contract: {exc}')
    return errors
