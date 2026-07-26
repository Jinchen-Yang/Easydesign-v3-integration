load ../../../../01-target-preparation/attempt-0001/artifacts/target.cif, target_user_regions
hide everything, target_user_regions
show cartoon, target_user_regions
color gray70, target_user_regions
select target_user_regions_region_1, target_user_regions and ((chain A and resi 32) or (chain A and resi 36) or (chain A and resi 39) or (chain A and resi 46) or (chain A and resi 50) or (chain A and resi 55) or (chain A and resi 59) or (chain A and resi 63) or (chain A and resi 66))
color red, target_user_regions_region_1
show sticks, target_user_regions_region_1
select target_user_regions_region_2, target_user_regions and ((chain A and resi 58) or (chain A and resi 61) or (chain A and resi 65) or (chain A and resi 69) or (chain A and resi 72) or (chain A and resi 76) or (chain A and resi 91) or (chain A and resi 95) or (chain A and resi 102) or (chain A and resi 105) or (chain A and resi 109) or (chain A and resi 113) or (chain A and resi 116) or (chain A and resi 120))
color blue, target_user_regions_region_2
show sticks, target_user_regions_region_2
select target_user_regions_region_3, target_user_regions and ((chain A and resi 99) or (chain A and resi 103) or (chain A and resi 106) or (chain A and resi 110) or (chain A and resi 114) or (chain A and resi 117) or (chain A and resi 121) or (chain A and resi 136) or (chain A and resi 140) or (chain A and resi 143) or (chain A and resi 147) or (chain A and resi 150) or (chain A and resi 154) or (chain A and resi 158))
color yellow, target_user_regions_region_3
show sticks, target_user_regions_region_3
orient
zoom visible
