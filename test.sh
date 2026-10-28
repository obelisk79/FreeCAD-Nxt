# 1. Is IOMMU on? (needs "AMD-Vi" lines; enable SVM + IOMMU in BIOS and add amd_iommu=on iommu=pt to kernel args if not)
sudo dmesg | grep -i -e AMD-Vi -e IOMMU | head
# 2. Is the 6900 XT in its own IOMMU group?
for g in /sys/kernel/iommu_groups/*; do echo "Group ${g##*/}:"; for d in $g/devices/*; do echo "  $(lspci -nns ${d##*/})"; done; done | grep -B1 -A3 -i navi
